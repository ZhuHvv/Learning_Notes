import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from dotenv import load_dotenv
import os, re
from openai import OpenAI
from lxml import etree

load_dotenv()  # 加载.env文件内容到环境变量中

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # 需要提前在.env文件中设置相关环境变量
        self.API_KEY = os.getenv("API_KEY")
        self.BASE_URL = os.getenv("BASE_URL")
        self.MODEL = os.getenv("MODEL")
        # 创建LLM client
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)
        # 存储历史消息
        self.messages = []
        # 读取提示词模板
        with open("./MCP_Prompt.txt", "r", encoding="utf-8") as file:
            self.system_prompt = file.read()

    async def connect_to_stdio_server(self, mcp_name, command: str, args: list[str], env: dict[str, str]={}):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()
        # 将MCP信息添加到system_prompt
        response = await self.session.list_tools()
        available_tools = ['##' + mcp_name + '\n### Available Tools\n- ' + tool.name + "\n" + tool.description + "\n" + json.dumps(tool.inputSchema) for tool in response.tools]
        self.system_prompt = self.system_prompt.replace("<$MCP_INFO$>", "\n".join(available_tools)+"\n<$MCP_INFO$>")
        tools = response.tools
        print(f"Successfully connected to {mcp_name} server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        self.messages.append(
            {
                "role": "system",
                "content": self.system_prompt
            }
        )
        self.messages.append(
            {
                "role": "user",
                "content": query
            }
        )

        # Initial Claude API call
        response = self.client.chat.completions.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=self.messages,
        )

        # Process response and handle tool calls
        final_text = []
        content = response.choices[0].message.content
        if'<use_mcp_tool>'notin content:
            final_text.append(content)
        else:
            # 解析tool_string
            server_name, tool_name, tool_args = self.parse_tool_string(content)

            # 执行工具调用
            result = await self.session.call_tool(tool_name, tool_args)
            print(f"[Calling tool {tool_name} with args {tool_args}]")
            print("-"*40)
            print("Server:", server_name)
            print("Tool:", tool_name)
            print("Args:", tool_args)
            print("-"*40)
            print("Result:", result.content[0].text)
            print("-"*40)
            self.messages.append({
                "role": "assistant",
                "content": content
            })
            self.messages.append({
                "role": "user",
                "content": f"[Tool {tool_name} \n returned: {result}]"
            })

            response = self.client.chat.completions.create(
                model=self.MODEL,
                max_tokens=1024,
                messages=self.messages
            )
            final_text.append(response.choices[0].message.content)
        return"\n".join(final_text)
    
    def parse_tool_string(self, tool_string: str) -> tuple[str, str, dict]:
        """
        解析大模型工具调用返回的字符串
        """
        tool_string = re.findall("(<use_mcp_tool>.*?</use_mcp_tool>)", tool_string, re.S)[0]
        root = etree.fromstring(tool_string)
        server_name = root.find('server_name').text
        tool_name = root.find('tool_name').text
        try:
            tool_args = json.loads(root.find('arguments').text)
        except json.JSONDecodeError:
            raise ValueError("Invalid tool arguments")
        return server_name, tool_name, tool_args

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        self.messages = []
        whileTrue:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break
                if query.strip() == '':
                    print("Please enter a query.")
                    continue
                response = await self.process_query(query)
                print(response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    client = MCPClient()
    try:
        await client.connect_to_stdio_server('weather', 'python', ['weather.py'])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

