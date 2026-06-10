import sys
import argparse
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from jarvis.config import settings
from jarvis.utils.logging import logger
from jarvis.agent.loop import JarvisAgent
from jarvis.mcp.server import run_mcp_server

console = Console()

BANNER = """
[bold cyan]
      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
      ██║███████║██████╔╝██║   ██║██║███████╗
 ██   ██║██╔══██║██╔══██║╚██╗ ██╔╝██║╚════██║
 ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
[/bold cyan]
[bold white]   ★ Production-Grade Personal AI Assistant & MCP Server ★ [/bold white]
"""

def show_welcome(agent: JarvisAgent):
    """Displays the interactive chat session welcome banner and status."""
    console.print(BANNER)
    console.print(Panel(
        f"[green]*[/green] Gemini connection established (Model: [bold]{agent.model_name}[/bold])\n"
        f"[green]*[/green] Sandbox path whitelist: [bold]{settings.whitelist_paths[0] if settings.whitelist_paths else 'None'}[/bold]\n"
        f"[green]*[/green] Long-term memory loaded from: [bold]{settings.memory_file.name}[/bold]",
        title="[bold cyan]System Initialization[/bold cyan]",
        expand=False
    ))
    
    # Display learned facts
    facts = agent.long_term_memory.get_facts()
    if facts:
        console.print("\n[bold yellow]🧠 Learned Facts in Long-term Memory:[/bold yellow]")
        for f in facts:
            console.print(f"  • {f}")
    console.print("\n[bold]Type your command in natural language. Type 'exit' or 'quit' to end session.[/bold]\n")

def run_chat_cli():
    """Runs the main interactive terminal chat loop with Jarvis."""
    try:
        agent = JarvisAgent(is_interactive=True)
    except ValueError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Initialization Error:[/bold red] {e}")
        sys.exit(1)

    show_welcome(agent)

    while True:
        try:
            # Command Prompt
            user_input = console.input("[bold cyan]Jarvis[/bold cyan] > ").strip()
            if not user_input:
                continue
                
            if user_input.lower() in ("exit", "quit"):
                console.print("[bold yellow]Shutting down Jarvis. Goodbye![/bold yellow]")
                break
                
            # Process query inside a beautiful console status spinner
            with console.status("[bold green]Thinking...[/bold green]", spinner="dots") as status:
                agent_generator = agent.run(user_input)
                
                # Consume status events (like tool calls) and update the spinner text dynamically
                event = None
                while True:
                    try:
                        if event is not None and event.get("type") == "confirmation_request":
                            # Temporarily stop status spinner so it doesn't corrupt inputs
                            status.stop()
                            
                            console.print(f"\n[bold yellow]⚠️  SECURITY WARNING:[/bold yellow] Jarvis wants to perform a dangerous action:")
                            console.print(f"  [cyan]{event['description']}[/cyan]")
                            
                            response = console.input("[bold green]Do you want to allow this action? (y/N): [/bold green]").strip().lower()
                            approved = response in ("y", "yes")
                            
                            # Restart status spinner
                            status.start()
                            status.update("[bold yellow]Resuming execution...[/bold yellow]")
                            
                            event = agent_generator.send(approved)
                        else:
                            event = next(agent_generator)
                            
                        if isinstance(event, dict):
                            if event.get("type") == "tool_call":
                                status.update(
                                    f"[bold yellow]🔧 Executing tool: [cyan]{event['name']}[/cyan] ...[/bold yellow]"
                                )
                                # Temporarily print tool calls above status for visibility
                                logger.info(f"Tool call detected: {event['name']}({event.get('arguments', {})})")
                            elif event.get("type") == "tool_result":
                                status.update(
                                    f"[bold green]* Tool [cyan]{event['name']}[/cyan] finished.[/bold green]"
                                )
                    except StopIteration as stop:
                        final_response = stop.value
                        break

            # Print final response beautifully rendered as markdown
            console.print("\n[bold purple]Jarvis Response:[/bold purple]")
            console.print(Markdown(final_response))
            console.print("") # spacing
            
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Session interrupted. Goodbye![/bold yellow]")
            break
        except Exception as e:
            console.print(f"\n[bold red]Error in Agent execution loop:[/bold red] {e}")
            logger.error("CLI Agent Loop exception", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="Jarvis - Personal AI Agent and MCP Server")
    group = parser.add_mutually_exclusive_group()
    
    group.add_argument(
        "--mcp",
        action="store_true",
        help="Start Jarvis in Model Context Protocol (MCP) server mode"
    )
    group.add_argument(
        "--cli",
        action="store_true",
        help="Start Jarvis in interactive CLI terminal chat mode"
    )
    group.add_argument(
        "--server",
        action="store_true",
        help="Start Jarvis local HTTP server for web clients"
    )
    group.add_argument(
        "--add-fact",
        type=str,
        metavar="FACT",
        help="Directly record a fact into long-term memory"
    )
    group.add_argument(
        "--remove-fact",
        type=str,
        metavar="FACT",
        help="Directly remove a fact from long-term memory"
    )
    
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Use SSE (HTTP/Server-Sent Events) transport instead of default stdio when running MCP server"
    )
    
    args = parser.parse_args()

    if args.mcp:
        # Start MCP Server
        transport = "sse" if args.sse else "stdio"
        try:
            run_mcp_server(transport=transport)
        except Exception as e:
            console.print(f"[bold red]Failed to start MCP server:[/bold red] {e}")
            sys.exit(1)
            
    elif args.server:
        # Run only the HTTP Web Server
        try:
            from jarvis.ui.app import run_local_server
            from jarvis.ui.app import find_free_port
            web_dir = Path(__file__).parent / "ui" / "web"
            port = 52254
            console.print(f"[bold green]*[/bold green] Starting Jarvis Web Server on: http://127.0.0.1:{port}/index.html")
            run_local_server(web_dir, port)
        except Exception as e:
            console.print(f"[bold red]Failed to start server:[/bold red] {e}")
            sys.exit(1)
            
    elif args.add_fact:
        # Save a fact directly
        try:
            agent = JarvisAgent(is_interactive=False)
            agent.learn_fact(args.add_fact)
            console.print(f"[bold green]Fact added successfully:[/bold green] '{args.add_fact}'")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)
            
    elif args.remove_fact:
        # Delete a fact directly
        try:
            agent = JarvisAgent(is_interactive=False)
            agent.forget_fact(args.remove_fact)
            console.print(f"[bold green]Fact removed successfully:[/bold green] '{args.remove_fact}'")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            sys.exit(1)
            
    elif args.cli:
        # Run Interactive Chat CLI
        run_chat_cli()
        
    else:
        # Default: Run Desktop GUI App
        try:
            from jarvis.ui.app import start_gui
            start_gui()
        except Exception as e:
            console.print(f"[bold red]Failed to start desktop GUI:[/bold red] {e}")
            console.print("Falling back to CLI Chat mode...\n")
            run_chat_cli()

if __name__ == "__main__":
    main()
