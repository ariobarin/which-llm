from __future__ import annotations

_spec = globals().get("__spec__")
_RUN_STDLIB_PROFILE = __name__ == "profile" or (
    __name__ == "__main__"
    and _spec is not None
    and getattr(_spec, "name", None) == "profile"
)

if _RUN_STDLIB_PROFILE:
    import importlib.util
    import sysconfig
    from pathlib import Path

    stdlib_profile = Path(sysconfig.get_path("stdlib")) / "profile.py"
    spec = importlib.util.spec_from_file_location("_stdlib_profile", stdlib_profile)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load stdlib profile module from {stdlib_profile}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    globals().update(
        (name, getattr(module, name))
        for name in dir(module)
        if not name.startswith("__")
    )
    if __name__ == "__main__":
        module.main()
else:
    import argparse
    import json

    import which_llm_core as core

    def main() -> int:
        parser = argparse.ArgumentParser(
            description="Inspect one LLM profile.",
        )
        parser.add_argument("model", help="Model slug, name, or OpenRouter slug.")
        core.add_output_args(parser)
        args = parser.parse_args()

        row = core.resolve_one(args.model)
        if args.format == "json":
            print(json.dumps(core.json_record(row), indent=2, default=str))
            core.print_snapshot_footer(args.format)
            return 0
        print(core.profile_text(row))
        core.print_snapshot_footer(args.format)
        return 0


    if __name__ == "__main__":
        raise SystemExit(main())
