import importlib.util
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FontDataBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        spec = importlib.util.spec_from_file_location("font_data", Path(self.root, "tools", "font_data.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # .gitignore excludes the fonts, so they are added as artifacts.
        build_data["artifacts"] += [f"/{path.relative_to(self.root).as_posix()}" for path in module.fetch_fonts()]
