#!/usr/bin/env python3
"""
🐈 Nanobot Dashboard v2 — Single-file web UI
Avvio:  python3.13 ~/nanobot_dashboard.py
Test:   PORT=8091 python3.13 ~/nanobot_dashboard.py
Accesso: http://picoclaw.local:8090
"""

import asyncio
import functools
import hashlib
import http.client
import io
import json
import os
import zipfile
import re
import secrets
import subprocess
import time
import urllib.request
import shlex
import ssl
import sqlite3
from datetime import datetime as _dt
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

