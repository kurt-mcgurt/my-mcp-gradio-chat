import gradio as gr
import asyncio
import json
import os
import sys
import logging
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack
import subprocess
import traceback

import google.generativeai as genai # WRONG
from google.generativeai import types # WRONG
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY")) # WRONG

class MCPGradioClient:
    def __init__(self):
        self.sessions = {}
        self.exit_stacks = {}
        self.model = genai.GenerativeModel('gemini-2.5-flash') # WRONG
        self.mcp_tools = []
        self.server_status = {}
        
    async def start_server(self, server_name: str, server_config: dict):
        """Start an individual MCP server with better error handling"""
        try:
            logger.info(f"Starting {server_name} server...")
            
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
            
            # Special handling for uvx commands - ensure PATH is set
            if command == "uvx":
                # Add cargo bin to PATH if it exists
                cargo_bin = os.path.expanduser("~/.cargo/bin")
                if os.path.exists(cargo_bin):
                    processed_env["PATH"] = f"{cargo_bin}:{processed_env.get('PATH', '')}"
                
                # Try to find uvx in common locations
                uvx_locations = [
                    "/home/codespace/.cargo/bin/uvx",
                    "/usr/local/bin/uvx",
                    "/home/codespace/.local/bin/uvx",
                    os.path.expanduser("~/.cargo/bin/uvx")
                ]
                
                for loc in uvx_locations:
                    if os.path.exists(loc):
                        command = loc
                        break
            
            # Create server parameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=processed_env
            )
            
            logger.info(f"Running command: {command} {' '.join(args)}")
            
            # Start the server with timeout
            try:
                stdio_transport = await asyncio.wait_for(
                    exit_stack.enter_async_context(stdio_client(server_params)),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Timeout starting {server_name}")
                self.server_status[server_name] = "timeout"
                return False
            
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
            
            logger.info(f"✅ Started {server_name} with {len(tools_response.tools)} tools")
            for tool in tools_response.tools:
                logger.info(f"  - {tool.name}: {tool.description[:100]}...")
            
            self.server_status[server_name] = "running"
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start {server_name}: {str(e)}")
            logger.error(traceback.format_exc())
            self.server_status[server_name] = f"failed: {str(e)}"
            
            # Clean up on failure
            if server_name in self.exit_stacks:
                try:
                    await self.exit_stacks[server_name].aclose()
                except:
                    pass
                del self.exit_stacks[server_name]
            
            return False
    
    async def start_all_servers(self):
        """Start all MCP servers from config"""
        # Load configuration
        with open('mcp_config.json', 'r') as f:
            config = json.load(f)
        
        # Start each server sequentially to avoid conflicts
        for server_name, server_config in config['mcpServers'].items():
            try:
                await self.start_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Exception starting {server_name}: {e}")

    # ========================================================================================================================================
    # PRETTY SURE ALL OF THE FOLLOWING CODE IS BASED ON `google-generativeai`, a deprecated package/SDK
    # WE NEED TO SOLE USE `google-genai` the current Python SDK, using this documentation: https://googleapis.github.io/python-genai/
    # ========================================================================================================================================
    #     # Collect all tools from successfully started sessions
    #     self.mcp_tools = []
    #     for server_name, session in self.sessions.items():
    #         try:
    #             tools_response = await session.list_tools()
    #             for tool in tools_response.tools:
    #                 # Add server name to tool for identification
    #                 tool_dict = {
    #                     "name": f"{server_name}__{tool.name}",
    #                     "description": tool.description,
    #                     "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
    #                     "server": server_name,
    #                     "original_name": tool.name
    #                 }
    #                 self.mcp_tools.append(tool_dict)
    #         except Exception as e:
    #             logger.error(f"Error collecting tools from {server_name}: {e}")
        
    #     # Report status
    #     logger.info("\n=== Server Status Summary ===")
    #     for server, status in self.server_status.items():
    #         logger.info(f"{server}: {status}")
    #     logger.info(f"Total tools available: {len(self.mcp_tools)}")
    
    # async def chat(self, message: str, history: List[List[str]]) -> tuple:
    #     """Process a chat message using Gemini with MCP tools"""
    #     try:
    #         # Prepare conversation history
    #         messages = []
    #         for user_msg, assistant_msg in history:
    #             messages.append(types.Content(role="user", parts=[types.Part(text=user_msg)]))
    #             if assistant_msg:
    #                 messages.append(types.Content(role="model", parts=[types.Part(text=assistant_msg)]))
            
    #         # Add current message
    #         messages.append(types.Content(role="user", parts=[types.Part(text=message)]))
            
    #         # Prepare tools for Gemini
    #         function_declarations = []
    #         for tool in self.mcp_tools:
    #             # Clean up parameters for Gemini
    #             params = tool.get("parameters", {})
    #             if "properties" in params:
    #                 # Convert MCP schema to Gemini function declaration
    #                 func_decl = types.FunctionDeclaration(
    #                     name=tool["name"],
    #                     description=tool["description"],
    #                     parameters=params
    #                 )
    #                 function_declarations.append(func_decl)
            
    #         # Configure tools
    #         tools = [types.Tool(function_declarations=function_declarations)] if function_declarations else None
            
    #         # WRONG:
    #         response = await self.model.generate_content_async( # WRONG
    #             messages, # WRONG
    #             tools=tools, # WRONG
    #             tool_config=types.ToolConfig( # WRONG
    #                 function_calling_config=types.FunctionCallingConfig( # WRONG
    #                     mode=types.FunctionCallingConfig.Mode.AUTO # WRONG
    #                 ) # WRONG
    #             ) if tools else None # WRONG
    #         ) # WRONG
            
    #         # Handle function calls
    #         if response.candidates and response.candidates[0].function_calls: # WRONG
    #             function_results = [] # WRONG
                
    #             for fc in response.candidates[0].function_calls: # WRONG 
    #                 tool_name = fc.name # WRONG 
    #                 args = fc.args or {} # WRONG
                    
    #                 if "__" in tool_name: # WRONG
    #                     server_name, original_name = tool_name.split("__", 1) # WRONG
    #                 else: # WRONG
    #                     continue # WRONG
                    
    #                 # Call the MCP tool
    #                 if server_name in self.sessions:
    #                     try:
    #                         result = await self.sessions[server_name].call_tool(
    #                             original_name, 
    #                             args
    #                         )
    #                         function_results.append(
    #                             types.FunctionResponse(
    #                                 name=tool_name,
    #                                 response={"result": str(result.content)}
    #                             )
    #                         )
    #                     except Exception as e:
    #                         function_results.append(
    #                             types.FunctionResponse(
    #                                 name=tool_name,
    #                                 response={"error": str(e)}
    #                             )
    #                         )
                
    #             # Get final response with function results
    #             messages.append(response.candidates[0].content)
    #             messages.append(types.Content(
    #                 role="user",
    #                 parts=[types.Part(function_response=fr) for fr in function_results]
    #             ))
                
    #             final_response = await self.model.generate_content_async(messages)
    #             response_text = final_response.text
    #         else:
    #             response_text = response.text
            
    #         # Update history
    #         history.append([message, response_text])
    #         return history, ""
            
    #     except Exception as e:
    #         error_msg = f"Error: {str(e)}"
    #         logger.error(f"Chat error: {error_msg}")
    #         history.append([message, error_msg])
    #         return history, ""
    
    async def cleanup(self):
        """Clean up all MCP sessions"""
        for server_name, exit_stack in self.exit_stacks.items():
            try:
                await exit_stack.aclose()
            except:
                pass

    def get_status_message(self):
        """Get a formatted status message"""
        status_lines = ["### MCP Server Status\n"]
        for server, status in self.server_status.items():
            emoji = "✅" if status == "running" else "❌"
            status_lines.append(f"{emoji} **{server}**: {status}")
        status_lines.append(f"\n📊 **Total tools available**: {len(self.mcp_tools)}")
        return "\n".join(status_lines)

# Global client instance
client = None

async def initialize_client():
    """Initialize the MCP client and start servers"""
    global client
    client = MCPGradioClient()
    await client.start_all_servers()
    return client

# ==========================================================================================
# VERY LIKELY THAT THE GRADIO CODE IS ALSO EXTREMELY OUTDATED AND BROKEN, BUT I'M NOT SURE
# ==========================================================================================
# def create_interface():
#     """Create the Gradio interface"""
#     with gr.Blocks(title="MCP-Powered Gemini Chat", theme=gr.themes.Soft()) as demo:
#         gr.Markdown("""
#         # 🤖 MCP-Powered Gemini Chat
        
#         Chat with Google Gemini enhanced with MCP tools:
#         - 📁 **Filesystem**: Read/write files
#         - 🔍 **Git-Repo-Research**: Search GitHub repositories  
#         - 🌿 **Git**: Run Git commands
#         - 📚 **Context7**: Get up-to-date documentation
#         """)
        
#         # Add status display
#         status_display = gr.Markdown()
        
#         chatbot = gr.Chatbot(height=500)
#         msg = gr.Textbox(
#             label="Message",
#             placeholder="Ask me anything! I can help with files, Git, documentation, and more...",
#             lines=2
#         )
        
#         with gr.Row():
#             submit = gr.Button("Send", variant="primary")
#             clear = gr.Button("Clear Chat")
#             refresh_status = gr.Button("Refresh Status")
        
#         async def respond(message, history):
#             if client:
#                 return await client.chat(message, history)
#             else:
#                 return history + [[message, "Error: MCP servers not initialized"]], ""
        
#         def update_status():
#             if client:
#                 return client.get_status_message()
#             return "MCP servers not initialized"
        
#         # Event handlers
#         msg.submit(respond, [msg, chatbot], [chatbot, msg])
#         submit.click(respond, [msg, chatbot], [chatbot, msg])
#         clear.click(lambda: None, None, chatbot, queue=False)
#         refresh_status.click(update_status, None, status_display)
        
#         # Initial status update
#         demo.load(update_status, None, status_display)
    
#     return demo

# Main execution
if __name__ == "__main__":
    # Run initialization
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Initialize client
        loop.run_until_complete(initialize_client())
        
        # Create and launch Gradio interface
        demo = create_interface()
        demo.launch(share=True, server_port=7860, server_name="0.0.0.0")
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if client:
            loop.run_until_complete(client.cleanup())