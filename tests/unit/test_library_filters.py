import time
from datetime import datetime, timedelta
from pathlib import Path

from overload.library.filters import FilterCriteria, apply_filter
from overload.library.models import MediaEntry, MediaType


def _e(name, media_type=MediaType.VIDEO, size=1000, mtime=None, duration=None, ext=None):
    mtime = mtime or time.time()
    ext = ext or Path(name).suffix.lower()
    return MediaEntry(
        path=Path(name),
        filename=Path(name).name,
        media_type=media_type,
        extension=ext,
        size=size,
        mtime=mtime,
        duration=duration,
    )


def test_filter_by_type():
    entries = [_e("a.mp4", MediaType.VIDEO), _e("b.mp3", MediaType.AUDIO), _e("c.jpg", MediaType.IMAGE)]
    crit = FilterCriteria(media_types=[MediaType.VIDEO])
    assert len(apply_filter(entries, crit)) == 1


def test_filter_by_size():
    entries = [_e("a.mp4", size=10_000), _e("b.mp4", size=1_000_000)]
    assert len(apply_filter(entries, FilterCriteria(min_size=100_000))) == 1
    assert len(apply_filter(entries, FilterCriteria(max_size=10_000))) == 1


def test_filter_by_date():
    now = time.time()
    old = now - 90 * 86400  # 3 mois
    entries = [_e("recent.mp4", mtime=now), _e("old.mp4", mtime=old)]
    crit = FilterCriteria(after=datetime.fromtimestamp(now - 86400))
    assert len(apply_filter(entries, crit)) == 1
    assert apply_filter(entries, crit)[0].filename == "recent.mp4"


def test_filter_by_duration():
    entries = [_e("short.mp4", duration=30), _e("long.mp4", duration=600), _e("nodur.mp4", duration=None)]
    assert len(apply_filter(entries, FilterCriteria(min_duration=60))) == 1
    assert len(apply_filter(entries, FilterCriteria(max_duration=60))) == 1
    # sans durée exclu si on filtre par durée
    assert len(apply_filter(entries, FilterCriteria(min_duration=0, max_duration=1000))) == 2


def test_filter_by_query():
    entries = [_e("vacances_ete.mp4"), _e("travail.pdf", MediaType.OTHER)]
    assert len(apply_filter(entries, FilterCriteria(query="vacances"))) == 1
    assert len(apply_filter(entries, FilterCriteria(query="VACANCES"))) == 1  # insensible casse
    assert len(apply_filter(entries, FilterCriteria(query="inexistant"))) == 0


def test_filter_query_and_type_combined():
    entries = [_e("a.mp4", MediaType.VIDEO), _e("a.mp3", MediaType.AUDIO)]
    crit = FilterCriteria(query="a", media_types=[MediaType.VIDEO])
    assert len(apply_filter(entries, crit)) == 1


def test_retrouver_plusieurs_mois():
    """Simulation du cas d'usage phare : retrouver un fichier de plusieurs mois."""
    now = datetime.now()
    entries = [
        _e("vacances_aout_2024.mp4", mtime=(now - timedelta(days=120)).timestamp()),
        _e("vacances_juillet_2024.mp4", mtime=(now - timedelta(days=150)).timestamp()),
        _e("clip_recent.mp4", mtime=now.timestamp()),
    ]
    crit = FilterCriteria(query="vacances", after=now - timedelta(days=180), before=now)
    result = apply_filter(entries, crit)
    assert len(result) == 2
    # Tri par mtime DESC : le plus récent des vacances d'abord
    crit2 = FilterCriteria(query="vacances", order_by="mtime", descending=True)
    result2 = apply_filter(entries, crit2)
    assert result2[0].filename == "vacances_aout_2024.mp4"


def test_normalized_for_db():
    crit = FilterCriteria(query=" test ", media_types=[MediaType.IMAGE], min_size=100, order_by="size")
    n = crit.normalized()
    assert n["query"] == "test"
    assert n["min_size"] == 100
    assert n["order_by"] == "size"
