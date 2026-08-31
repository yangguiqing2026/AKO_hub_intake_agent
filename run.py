"""服务启动入口。"""

from __future__ import annotations

import uvicorn

from ako_intake.config import load_config


def main() -> None:
    config = load_config()
    uvicorn.run("app:app", host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()

