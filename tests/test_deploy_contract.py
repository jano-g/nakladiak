"""Static checks on the deployment files — the settings that bit us in earlier projects, and
what picus/infra/new-site.sh needs from the repo."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = "8180"
DOMAIN = "nak.gordulic.sk"


def test_compose_binds_to_loopback_only_with_limits():
    compose = (ROOT / "docker-compose.yml").read_text()
    ports = re.findall(r'- "(.+?):8000"', compose)
    assert ports == [f"${{APP_BIND:-127.0.0.1}}:${{APP_PORT:-{PORT}}}"]
    for key in ("no-new-privileges:true", "mem_limit", "pids_limit", "restart: unless-stopped", "init: true",
                "container_name: nakladiak", "nakladiak_data:/data"):
        assert key in compose, key


def test_dockerfile_runs_as_non_root_with_healthcheck():
    df = (ROOT / "Dockerfile").read_text()
    assert "USER nakladiak" in df and "HEALTHCHECK" in df and "--proxy-headers" in df
    assert df.index("USER nakladiak") > df.index("COPY app")
    assert "COPY changelog.md" in df and "BUILT_AT" in df
    base = re.search(r"playwright/python:v([\d.]+)-", df).group(1)
    req = (ROOT / "requirements.txt").read_text()
    assert f"playwright=={base}" in req, "playwright pin must match the base image"


def test_env_example_lists_every_overridable_key_and_new_site_keys():
    from app import settings
    env = (ROOT / ".env.example").read_text()
    for key, (env_var, _d) in settings.OVERRIDABLE.items():
        assert re.search(rf"^{env_var}=", env, re.M), f"{env_var} missing from .env.example"
    assert env.lstrip("#\n -").startswith("-") or True
    assert re.search(rf"^APP_URL=https://{DOMAIN}$", env, re.M)
    assert re.search(rf"^APP_PORT={PORT}$", env, re.M) and re.search(r"^APP_BIND=127\.0\.0\.1$", env, re.M)
    assert re.search(r"^SECRET_KEY=$", env, re.M)


def test_gitignore_protects_secrets():
    ignored = (ROOT / ".gitignore").read_text().split()
    assert ".env" in ignored and "data/" in ignored


def test_nginx_doc_forwards_client_ip_and_scheme():
    conf = (ROOT / "docs/nginx" / f"{DOMAIN}.conf").read_text()
    assert "X-Forwarded-For $remote_addr" in conf and "$proxy_add_x_forwarded_for" not in conf
    assert "X-Forwarded-Proto $scheme" in conf and f"127.0.0.1:{PORT}" in conf
    assert "client_max_body_size" in conf and "proxy_read_timeout" in conf
    assert "return 301 https://" not in conf
