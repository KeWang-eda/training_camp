"""Terminal entry point for the LangChain chatbot."""

import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chatbot.terminal_chatbot_core import TerminalChatbotCore
from terminal.command_handler import CommandHandler
from terminal.stream_handler import TerminalStreamHandler

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Run the terminal chatbot interface.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="script_file",
        help="Path to a command script (.tcl/.txt) to execute before exiting.",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        help="Path to script execution log (defaults to config.paths.script_log).",
    )
    return parser.parse_args()


def load_config(path: Path) -> Dict[str, Any]:
    """Load YAML configuration if present."""

    if not path.exists():
        return {}

    with open(path, 'r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def resolve_setting(
    config_value: Optional[str],
    env_keys: tuple,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Resolve a setting from config first, then env, then fallback."""

    if config_value:
        return config_value

    for key in env_keys:
        value = os.environ.get(key)
        if value:
            return value

    return fallback


def build_status_callback(console: Console):
    """Create a status callback that forwards messages to the console."""

    def _callback(level: str, message: str) -> None:
        styles = {
            'info': 'blue',
            'warning': 'yellow',
            'success': 'green',
            'error': 'red',
        }
        color = styles.get(level, 'white')
        console.print(f"[{color}]{message}[/{color}]")

    return _callback


def handle_chat_message(
    chatbot: TerminalChatbotCore,
    console: Console,
    prompt: str,
    use_rag: Optional[bool] = None,
) -> None:
    """Send a prompt to the chatbot and stream the response."""

    console.print(f"[bold blue]You:[/bold blue] {prompt}")
    stream_handler = TerminalStreamHandler(console)

    try:
        response_text = chatbot.ask(prompt, stream_handler=stream_handler, use_rag=use_rag)
        if not stream_handler.get_full_response() and response_text:
            console.print(response_text)
    except Exception as exc:  # pragma: no cover - runtime feedback
        console.print(f"[red]Failed to generate response: {exc}[/red]")


def run_script_file(
    script_path: str,
    chatbot: TerminalChatbotCore,
    command_handler: CommandHandler,
    console: Console,
    log_path: Path,
) -> None:
    """Execute commands from a script file sequentially."""

    script_file = Path(script_path).expanduser()
    if not script_file.exists():
        console.print(f"[red]Script file not found: {script_file}[/red]")
        return

    if script_file.suffix.lower() not in {'.tcl', '.txt'}:
        console.print(f"[red]Unsupported script extension {script_file.suffix}. Use .tcl or .txt.[/red]")
        return

    log_path = log_path.expanduser()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        console.print(f"[yellow]Failed to prepare log directory {log_path.parent}: {exc}[/yellow]")

    with script_file.open('r', encoding='utf-8') as handle, log_path.open('a', encoding='utf-8') as log:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue

            timestamp = datetime.now().isoformat()
            log.write(f"[{timestamp}] CMD#{line_no}: {line}\n")
            try:
                console.print(f"[dim]script > {line}[/dim]")
                if line.startswith('/'):
                    should_continue, payload = command_handler.process(line)
                    log.write(f"[{timestamp}] RESULT: command executed.\n")
                    if payload and payload.get('prompt'):
                        handle_chat_message(
                            chatbot,
                            console,
                            payload['prompt'],
                            use_rag=payload.get('use_rag'),
                        )
                        log.write(f"[{timestamp}] RESULT: custom command prompt sent.\n")
                    if not should_continue:
                        log.write(f"[{timestamp}] INFO: script requested exit.\n\n")
                        return
                else:
                    handle_chat_message(chatbot, console, line)
                    log.write(f"[{timestamp}] RESULT: chat executed.\n")
            except Exception as exc:  # pragma: no cover - script mode
                console.print(f"[red]Script command failed (line {line_no}): {exc}[/red]")
                log.write(f"[{timestamp}] ERROR: {exc}\n")
                log.write(traceback.format_exc())
                log.write("\n")
                return

            log.write("\n")
        log.write(f"[{datetime.now().isoformat()}] INFO: script completed.\n\n")


def main() -> None:
    """Run the terminal chatbot REPL."""

    args = parse_args()
    console = Console()

    config_path = Path(args.config)
    script_path_arg = args.script_file
    script_log_arg = args.log_file
    config = load_config(config_path)
    app_config = config.get('app', {})
    commands_config = config.get('commands', {})
    feishu_config = config.get('feishu', {})
    testcase_modes = config.get('testcase_modes', {})
    testcase_layouts = config.get('testcase_layouts', {})
    evaluation_metrics = config.get('evaluation_metrics', [])
    evaluation_config = config.get('evaluation', {})
    review_metrics = evaluation_config.get('review_metrics', [])
    outputs_config = config.get('outputs', {})
    processing_config = config.get('processing', {})
    testcase_output_cfg = outputs_config.get('testcases', {})
    evaluations_output_cfg = outputs_config.get('evaluations', {})
    default_case_format = testcase_output_cfg.get('default_format', 'json')
    default_case_dir = testcase_output_cfg.get('default_dir')
    default_eval_dir = evaluations_output_cfg.get('default_dir')
    paths_config = config.get('paths', {})
    latest_cache_path = paths_config.get('latest_testcase_cache')
    script_log_default = paths_config.get('script_log')
    image_prompt_config = config.get('image_prompts', {})
    embedding_model_name = processing_config.get('embedding_model')
    text_splitter_config = processing_config.get('text_splitter', {})

    api_key = resolve_setting(
        app_config.get('api_key'),
        ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"),
    )
    base_url = resolve_setting(
        app_config.get('default_base_url'),
        ("KIMI_BASE_URL",),
        "https://api.moonshot.cn/v1",
    )
    model_name = resolve_setting(
        app_config.get('default_model'),
        ("KIMI_MODEL",),
        "kimi-k2-turbo-preview",
    )
    image_api_key = resolve_setting(
        app_config.get('image_api_key'),
        ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "KIMI_API_KEY"),
        api_key,
    )
    image_base_url = resolve_setting(
        app_config.get('image_base_url'),
        ("KIMI_IMAGE_BASE_URL",),
        base_url,
    )
    image_model_name = resolve_setting(
        app_config.get('image_model'),
        ("KIMI_IMAGE_MODEL",),
        model_name,
    )
    system_prompt = app_config.get('system_prompt')

    if not api_key:
        console.print("[red]API key not provided. Set it in config.yaml or via KIMI_API_KEY.[/red]")
        sys.exit(1)

    import json as _json
    import hashlib

    config_hash = hashlib.sha256(
        _json.dumps(config, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()[:12]

    status_callback = build_status_callback(console)
    chatbot = TerminalChatbotCore(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        image_api_key=image_api_key,
        image_base_url=image_base_url,
        image_model_name=image_model_name,
        system_prompt=system_prompt,
        image_prompt_config=image_prompt_config,
        history_limit=app_config.get('history_limit', 50),
        status_callback=status_callback,
        feishu_app_id=feishu_config.get('app_id'),
        feishu_app_secret=feishu_config.get('app_secret'),
        feishu_base_url=feishu_config.get('base_url', 'https://open.feishu.cn'),
        testcase_modes=testcase_modes,
        testcase_layouts=testcase_layouts,
        default_testcase_format=default_case_format,
        default_testcase_dir=default_case_dir,
        evaluation_output_dir=default_eval_dir,
        latest_testcase_cache=latest_cache_path,
        embedding_model_name=embedding_model_name,
        text_splitter_config=text_splitter_config,
        config_hash=config_hash,
        evaluation_metrics=evaluation_metrics,
        review_metrics=review_metrics,
    )

    command_handler = CommandHandler(
        chatbot,
        console,
        custom_commands=commands_config,
        default_case_format=default_case_format,
    )
    log_path = Path(script_log_arg or script_log_default or "./output/logs/shell.log")

    if script_path_arg:
        run_script_file(
            script_path_arg,
            chatbot,
            command_handler,
            console,
            log_path,
        )
        return

    session = PromptSession(history=InMemoryHistory())

    banner_text = app_config.get(
        'banner',
        "欢迎使用终端版 AI 助手！输入 /help 查看命令列表， 直接输入内容即可开始聊天。",
    )
    console.print(
        Panel(
            banner_text,
            title="LangChain Chatbot",
            border_style="cyan",
            subtitle=f"config: {config_path}",
        )
    )

    while True:
        try:
            user_input = session.prompt("chat > ")
        except KeyboardInterrupt:
            console.print("[dim]Press Ctrl-D or type /exit to quit.[/dim]")
            continue
        except EOFError:
            console.print("\n[bold]Goodbye![/bold]")
            break

        stripped = user_input.strip()
        if not stripped:
            continue

        if stripped.startswith('/'):
            should_continue, payload = command_handler.process(stripped)
            if not should_continue:
                break
            if payload and payload.get('prompt'):
                handle_chat_message(
                    chatbot,
                    console,
                    payload['prompt'],
                    use_rag=payload.get('use_rag'),
                )
            continue

        handle_chat_message(chatbot, console, stripped)


if __name__ == "__main__":
    main()
