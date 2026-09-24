"""让 `python -m kbx ...` 可用。"""

from .cli import main

raise SystemExit(main())
