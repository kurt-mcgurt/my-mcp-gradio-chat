import gradio as gr
import asyncio
import json
import os
import sys
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack, asynccontextmanager
import subprocess
import signal

import google.generativeai as genai
from google.generativeai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class MCPGradioClient:
    def __init__(self):
        self.sessions = {}
        self.exit_stacks = {}
        self.model = genai.GenerativeModel('gemini-2.5-pro')
        self.mcp_tools = []
        
    async def start_server(self, server_name: str, server_config: dict):
        """Start an individual MCP server"""
        try:
            # Create exit stack for this server
            exit_stack = AsyncExitStack()
            
            # Extract server parameters
            command = server_config["command"]
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            
            # Process environment variables
            processed_env = os.environ.copy()
            for key, value in env.items():
                # Replace environment variable references
                if value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    value = os.getenv(env_var, "")
                processed_env[key] = value
            
            # Replace environment variables in args
            # processed_args = []
            # for arg in args:
            #     if "${CODESPACE_NAME}" in arg:
            #         arg = arg.replace("${CODESPACE_NAME}", os.getenv("CODESPACE_NAME", ""))
            #     processed_args.append(arg)
            
            # Create server parameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=processed_env
            )
            
            # Start the server
            stdio_transport = await exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            session = await exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            
            await session.initialize()
            
            # Store session and exit stack
            self.sessions[server_name] = session
            self.exit_stacks[server_name] = exit_stack
            
            # Get available tools
            tools_response = await session.list_tools()
            
            print(f"✅ Started {server_name} with {len(tools_response.tools)} tools")
            for tool in tools_response.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to start {server_name}: {str(e)}")
            return False
    
    async def start_all_servers(self):
        """Start all MCP servers from config"""
        # Load configuration
        with open('mcp_config.json', 'r') as f:
            config = json.load(f)
        
        # Start each server
        for server_name, server_config in config['mcpServers'].items():
            await self.start_server(server_name, server_config)
        
        # Collect all tools from all sessions
        self.mcp_tools = []
        for server_name, session in self.sessions.items():
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                # Add server name to tool for identification
                tool_dict = {
                    "name": f"{server_name}__{tool.name}",
                    "description": tool.description,
                    "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    "server": server_name,
                    "original_name": tool.name
                }
                self.mcp_tools.append(tool_dict)
    
    async def chat(self, message: str, history: List[List[str]]) -> tuple:
        """Process a chat message using Gemini with MCP tools"""
        try:
            # Prepare conversation history
            messages = []
            for user_msg, assistant_msg in history:
                messages.append(types.Content(role="user", parts=[types.Part(text=user_msg)]))
                if assistant_msg:
                    messages.append(types.Content(role="model", parts=[types.Part(text=assistant_msg)]))
            
            # Add current message
            messages.append(types.Content(role="user", parts=[types.Part(text=message)]))
            
            # Prepare tools for Gemini
            function_declarations = []
            for tool in self.mcp_tools:
                # Clean up parameters for Gemini
                params = tool.get("parameters", {})
                if "properties" in params:
                    # Convert MCP schema to Gemini function declaration
                    func_decl = types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool["description"],
                        parameters=params
                    )
                    function_declarations.append(func_decl)
            
            # Configure tools
            tools = [types.Tool(function_declarations=function_declarations)] if function_declarations else None
            
            # Generate response
            response = await self.model.generate_content_async(
                messages,
                tools=tools,
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfig.Mode.AUTO
                    )
                ) if tools else None
            )
            
            # Handle function calls
            if response.candidates and response.candidates[0].function_calls:
                function_results = []
                
                for fc in response.candidates[0].function_calls:
                    tool_name = fc.name
                    args = fc.args or {}
                    
                    # Extract server and original tool name
                    if "__" in tool_name:
                        server_name, original_name = tool_name.split("__", 1)
                    else:
                        continue
                    
                    # Call the MCP tool
                    if server_name in self.sessions:
                        try:
                            result = await self.sessions[server_name].call_tool(
                                original_name, 
                                args
                            )
                            function_results.append(
                                types.FunctionResponse(
                                    name=tool_name,
                                    response={"result": str(result.content)}
                                )
                            )
                        except Exception as e:
                            function_results.append(
                                types.FunctionResponse(
                                    name=tool_name,
                                    response={"error": str(e)}
                                )
                            )
                
                # Get final response with function results
                messages.append(response.candidates[0].content)
                messages.append(types.Content(
                    role="user",
                    parts=[types.Part(function_response=fr) for fr in function_results]
                ))
                
                final_response = await self.model.generate_content_async(messages)
                response_text = final_response.text
            else:
                response_text = response.text
            
            # Update history
            history.append([message, response_text])
            return history, ""
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            history.append([message, error_msg])
            return history, ""
    
    async def cleanup(self):
        """Clean up all MCP sessions"""
        for server_name, exit_stack in self.exit_stacks.items():
            try:
                await exit_stack.aclose()
            except:
                pass

# Global client instance
client = None

async def initialize_client():
    """Initialize the MCP client and start servers"""
    global client
    client = MCPGradioClient()
    await client.start_all_servers()
    return client

def create_interface():
    """Create the Gradio interface"""
    with gr.Blocks(title="MCP-Powered Gemini Chat") as demo:
        gr.Markdown("""
        # 🤖 MCP-Powered Gemini Chat
        
        Chat with Google Gemini enhanced with MCP tools:
        - 📁 **Filesystem**: Read/write files
        - 🔍 **Git-Repo-Research**: Search GitHub repositories  
        - 🌿 **Git**: Run Git commands
        - 📚 **Context7**: Get up-to-date documentation
        
        Just chat naturally and the AI will use tools as needed!
        """)
        
        chatbot = gr.Chatbot(height=500)
        msg = gr.Textbox(
            label="Message",
            placeholder="Ask me anything! I can help with files, Git, documentation, and more...",
            lines=2
        )
        clear = gr.Button("Clear")
        
        async def respond(message, history):
            if client:
                return await client.chat(message, history)
            else:
                return history + [[message, "Error: MCP servers not initialized"]], ""
        
        msg.submit(respond, [msg, chatbot], [chatbot, msg])
        clear.click(lambda: None, None, chatbot, queue=False)
    
    return demo

# Main execution
if __name__ == "__main__":
    # Run initialization
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(initialize_client())
        
        # Create and launch Gradio interface
        demo = create_interface()
        demo.launch(share=True, server_port=7860)
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if client:
            loop.run_until_complete(client.cleanup())