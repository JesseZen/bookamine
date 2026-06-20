from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    return Settings(
        project_root=project_root,
        data_dir=project_root / "data",
    )
