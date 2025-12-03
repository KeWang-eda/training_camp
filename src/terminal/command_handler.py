"""Command handler for processing terminal commands."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class CommandHandler:
    """Handles built-in and custom commands for the terminal interface."""

    def __init__(
        self,
        chatbot_core,
        console: Console,
        custom_commands: Optional[Dict[str, Any]] = None,
        default_case_format: str = "json",
    ):
        """Initialize command handler."""

        self.chatbot_core = chatbot_core
        self.console = console
        self.custom_commands = custom_commands or {}
        self.default_case_format = default_case_format or "json"

    def process(self, user_input: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Process user input as a command."""

        if not user_input.startswith('/'):
            return True, None

        parts = user_input.split()
        command = parts[0][1:]
        args = parts[1:]

        try:
            if command in {"exit", "quit"}:
                return False, None
            if command == "help":
                self.show_help()
                return True, None
            if command == "clear":
                self.clear_screen()
                return True, None
            if command == "history":
                self.show_history()
                return True, None
            if command == "read":
                self.read_document(args)
                return True, None
            if command == "read_link":
                self.read_link(args)
                return True, None
            if command == "generate_cases":
                self.generate_cases(args)
                return True, None
            if command == "evaluate_cases":
                self.evaluate_cases(args)
                return True, None
            if command == "save":
                self.save_history(args)
                return True, None
            if command in self.custom_commands:
                payload = self.execute_custom_command(command, args)
                return True, payload

            self.console.print(f"[red]Unknown command: /{command}[/red]")
            self.console.print("Type /help to see available commands.")
            return True, None

        except Exception as exc:
            self.console.print(f"[red]Command execution failed: {exc}[/red]")
            return True, None

    def show_help(self) -> None:
        """Display command help information."""

        self.console.print("\n[bold cyan]Available Commands:[/bold cyan]\n")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Command", style="yellow", width=15)
        table.add_column("Description", style="white")
        table.add_column("Usage", style="dim")

        builtin_commands = [
            ("help", "Show this help message", "/help"),
            ("exit", "Exit the application", "/exit"),
            ("clear", "Clear the terminal", "/clear"),
            ("history", "Show conversation history", "/history"),
            ("read", "Read and index local files", "/read <path> [more_paths]"),
            ("read_link", "Fetch Feishu doc by link/id", "/read_link <url_or_id>"),
            ("generate_cases", "Generate test cases", "/generate_cases mode=default output=... format=json thoughts=false plan=false"),
            ("evaluate_cases", "Evaluate generated cases", "/evaluate_cases <baseline> <candidate> [output]"),
            ("save", "Save conversation history", "/save [filename]"),
        ]

        for name, desc, usage in builtin_commands:
            table.add_row(name, desc, usage)

        self.console.print(table)

        if self.custom_commands:
            custom_table = Table(show_header=True, header_style="bold magenta")
            custom_table.add_column("Command", style="yellow", width=15)
            custom_table.add_column("Description", style="white")

            for name, details in self.custom_commands.items():
                custom_table.add_row(name, details.get('description', 'No description'))

            self.console.print("\n[bold cyan]Custom Commands:[/bold cyan]\n")
            self.console.print(custom_table)

        self.console.print("\n[dim]Prefix every command with '/' to execute it.[/dim]\n")

    def clear_screen(self) -> None:
        self.console.clear()

    def show_history(self) -> None:
        history = self.chatbot_core.get_conversation_history()
        if not history:
            self.console.print("[yellow]No conversation history available.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Role", style="yellow", width=10)
        table.add_column("Message", style="white")

        for index, message in enumerate(history, start=1):
            role_label = "You" if message['role'] == 'user' else "Assistant"
            table.add_row(str(index), role_label, message['content'])

        self.console.print(table)

    def read_document(self, args: List[str]) -> None:
        if not args:
            self.console.print("[red]Please specify at least one file path: /read <file_path>[/red]")
            return

        resolved_paths: List[str] = []
        for arg in args:
            path = Path(arg).expanduser().resolve()
            if not path.exists():
                self.console.print(f"[yellow]Skipping missing path: {path}[/yellow]")
                continue
            if path.is_dir():
                self.console.print(f"[yellow]{path} is a directory and will be skipped.[/yellow]")
                continue
            resolved_paths.append(str(path))

        if not resolved_paths:
            self.console.print("[red]No valid files to read.[/red]")
            return

        self.console.print(f"[blue]Reading {len(resolved_paths)} file(s)...[/blue]")
        loaded_count = self.chatbot_core.ingest_local_files(resolved_paths)

        if loaded_count:
            self.console.print(
                f"[green]Successfully indexed {loaded_count} document(s). Ready for RAG queries.[/green]"
            )
        else:
            self.console.print("[red]Failed to process the provided files.[/red]")

    def read_link(self, args: List[str]) -> None:
        if not args:
            self.console.print("[red]Usage: /read_link <feishu_link_or_id>[/red]")
            return

        identifier = args[0]
        count = self.chatbot_core.ingest_feishu_document(identifier)
        if count:
            self.console.print(
                f"[green]Indexed {count} Feishu document(s). Ready for RAG queries.[/green]"
            )

    def generate_cases(self, args: List[str]) -> None:
        options = self._parse_generate_args(args)
        try:
            result_path, plan_notes, plan_sections = self.chatbot_core.run_testcase_generation(
                mode=options['mode'],
                output_path=options['output'],
                output_format=options['format'],
                show_thoughts=options['show_thoughts'],
                show_plan_summary=options['show_plan'],
            )
            if options['show_thoughts'] and plan_notes:
                body = "\n".join(f"{idx}. {plan}" for idx, plan in enumerate(plan_notes, start=1))
                self.console.print(
                    Panel(
                        body or "No planner output.",
                        title="Planner Thoughts",
                        expand=False,
                        style="cyan",
                    )
                )
            if options['show_plan'] and plan_sections:
                lines = []
                for section in plan_sections:
                    lines.append(f"[bold]{section['title']}[/bold]")
                    for item in section.get('checklist', []):
                        lines.append(f"- {item}")
                    lines.append("")
                body = "\n".join(lines).strip() or "No plan summary."
                self.console.print(
                    Panel(
                        body,
                        title="Test Plan",
                        expand=False,
                        style="magenta",
                    )
                )
        except Exception as exc:
            self.console.print(f"[red]Failed to generate test cases: {exc}[/red]")

    def evaluate_cases(self, args: List[str]) -> None:
        baseline = args[0] if args else None
        candidate = args[1] if len(args) > 1 else None
        output = args[2] if len(args) > 2 else None
        if len(args) > 3:
            self.console.print("[yellow]Warning: 多余参数将被忽略。[/yellow]")
        try:
            report_path = self.chatbot_core.run_evaluation(
                baseline_path=baseline,
                candidate_path=candidate,
                output_path=output,
            )
        except Exception as exc:
            self.console.print(f"[red]Failed to evaluate cases: {exc}[/red]")

    def save_history(self, args: List[str]) -> None:
        history = self.chatbot_core.get_conversation_history()
        if not history:
            self.console.print("[yellow]No conversation history to save.[/yellow]")
            return

        filename = args[0] if args else "conversation_history.txt"
        try:
            with open(filename, 'w', encoding='utf-8') as handle:
                for message in history:
                    role = message['role'].upper()
                    handle.write(f"{role}: {message['content']}\n\n")

            self.console.print(f"[green]Conversation history saved to: {filename}[/green]")
        except OSError as exc:
            self.console.print(f"[red]Failed to save history: {exc}[/red]")

    def execute_custom_command(self, command: str, args: List[str]) -> Optional[Dict[str, Any]]:
        command_config = self.custom_commands.get(command)
        if not command_config:
            self.console.print(f"[red]Custom command not found: {command}[/red]")
            return None

        prompt_template = command_config.get('prompt')
        if not prompt_template:
            self.console.print(f"[red]No prompt template for command: {command}[/red]")
            return None

        history_text = self._format_history_for_prompt()

        try:
            final_prompt = prompt_template.format(
                history=history_text,
                args=' '.join(args),
            )
        except KeyError as exc:
            self.console.print(f"[red]Missing variable {exc} in prompt template.[/red]")
            return None

        self.console.print(f"[blue]Executing custom command: /{command}[/blue]")
        return {
            'prompt': final_prompt,
            'label': command,
            'use_rag': command_config.get('use_rag'),
        }

    def _format_history_for_prompt(self) -> str:
        history = self.chatbot_core.get_conversation_history()
        if not history:
            return "No conversation history available."

        slices = history[-10:]
        return '\n'.join(f"{item['role']}: {item['content']}" for item in slices)

    def _parse_generate_args(self, args: List[str]) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            'mode': 'default',
            'output': None,
            'show_thoughts': False,
            'format': self.default_case_format,
            'show_plan': False,
        }
        positional: List[str] = []

        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                if key == 'mode' and value:
                    options['mode'] = value
                elif key == 'output' and value:
                    options['output'] = value
                elif key in {'thoughts', 'show_thoughts', 'show'}:
                    options['show_thoughts'] = self._parse_bool(value)
                elif key in {'plan', 'plan_summary'}:
                    options['show_plan'] = self._parse_bool(value)
                elif key == 'format' and value:
                    options['format'] = value.lower()
                else:
                    positional.append(arg)
            else:
                positional.append(arg)

        if positional:
            options['mode'] = positional[0]
        if len(positional) > 1:
            options['output'] = positional[1]
        if len(positional) > 2:
            options['show_thoughts'] = self._parse_bool(positional[2])
        if len(positional) > 3:
            options['format'] = positional[3].lower()
        if len(positional) > 4:
            options['show_plan'] = self._parse_bool(positional[4])

        if options['format'] in {'md'}:
            options['format'] = 'markdown'

        return options

    @staticmethod
    def _parse_bool(value: Optional[str]) -> bool:
        if value is None:
            return False
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}
