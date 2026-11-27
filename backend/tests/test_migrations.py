from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_single_alembic_head_and_expected_parent() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert len(heads) == 1
    revision = script.get_revision(heads[0])
    assert revision is not None
    # 当前 head 是删除 Refresh Session, 其父版本是删除订单支付字段.
    assert revision.down_revision == "5d7a27f8ba5c"
