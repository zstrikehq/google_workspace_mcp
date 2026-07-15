#!/bin/sh
set -e

# Fly volumes are always mounted root-owned; give the app user ownership
# at boot so new machines/volumes need no manual chown.
if [ -d /data ]; then
    chown -R app:app /data
fi

export HOME=/home/app
if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid app --regid app --init-groups \
        uv run main.py --transport streamable-http "$@"
fi
# ponytail: su fallback joins args with $* — fine for simple flags, no spaced args in CMD
exec su -s /bin/sh app -c "exec uv run main.py --transport streamable-http $*"
