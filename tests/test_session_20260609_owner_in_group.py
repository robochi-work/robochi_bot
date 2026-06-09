"""Regression test: owner_in_group check must use Status.OWNER.

Bug: vacancy/views.py used Status.MEMBER, but for vacancy owners the
chat_member handler writes Status.OWNER -> button "Group" disappeared
from owner's vacancy card.
"""


def test_owner_in_group_uses_owner_status():
    """The 'group invite' button visibility check must look for Status.OWNER."""
    from pathlib import Path

    src = Path("vacancy/views.py").read_text(encoding="utf-8")
    assert "user=vacancy.owner, group=vacancy.group, status=_TgStatus.OWNER" in src, (
        "vacancy_detail view must filter UserInGroup by Status.OWNER for the vacancy owner"
    )
    assert "status=_TgStatus.MEMBER" not in src.split("owner_in_group")[1].split("\n\n")[0], (
        "Owner-in-group check must NOT use Status.MEMBER (that's worker status)"
    )
