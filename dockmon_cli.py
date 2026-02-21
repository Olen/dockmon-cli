#!/usr/bin/env python

import argparse
import configparser
import json
import os
import shutil
import sys

import requests

from datetime import datetime


def get_docker_secret(secret_name):
    secret_path = os.path.join("/run/secrets", secret_name)
    try:
        with open(secret_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def get_config_file():
    """Read credentials from ~/.config/dockmon/config.ini if it exists."""
    config_path = os.path.expanduser("~/.config/dockmon/config.ini")
    if not os.path.exists(config_path):
        return None, None
    config = configparser.ConfigParser()
    config.read(config_path)
    url = config.get("api", "url", fallback=None)
    key = config.get("api", "key", fallback=None)
    return url, key


def resolve_credentials():
    """Resolve API credentials. Precedence: env vars > config file > Docker secrets."""
    api_key = os.getenv('DOCKMON_API_KEY')
    api_url = os.getenv('DOCKMON_API_URL')

    if not api_key:
        api_url, api_key = get_config_file()

    if not api_key:
        api_key = get_docker_secret('dockmon_api_key')
        api_url = get_docker_secret('dockmon_api_url')

    if not api_key or not api_url:
        print("Error: DOCKMON_API_KEY and DOCKMON_API_URL must be set via "
              "environment variables, ~/.config/dockmon/config.ini, or Docker secrets.",
              file=sys.stderr)
        sys.exit(1)

    return api_url, api_key



# ANSI color helpers
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"

def color_state(state: str) -> str:
    """Return colored emoji + text based on container state."""
    s = state.lower()
    if s == "running":
        return f"{C.GREEN}🟢 running{C.RESET}"
    if s == "exited":
        return f"{C.RED}🔴 exited{C.RESET}"
    if s == "paused":
        return f"{C.YELLOW}🟡 paused{C.RESET}"
    return f"{C.GRAY}⚪ {state}{C.RESET}"

def color_update(update: bool) -> str:
    if update['update_available']:
        text = f"⬆️ update to {update['latest_version']}"
        return f"{C.YELLOW}{text}{C.RESET}"
    else:
        text = f"✅ up to date"
        return f"{C.GREEN}{text}{C.RESET}"

def color_version(version: str) -> str:
    if version == 'N/A':
        return f"{C.YELLOW}{version}{C.RESET}"
    return f"{C.BLUE}{version}{C.RESET}"

def cli_format_containers(containers):
    """Pretty-print containers in a table with color and emojis."""
    if not containers:
        print(f"{C.YELLOW}⚠️  No containers found.{C.RESET}")
        print()
        return

    # Determine column widths
    width = shutil.get_terminal_size((100, 20)).columns
    name_w = max(max(len(c.name) for c in containers), 9) + 2
    image_w = max(len(c.image) for c in containers) + 2
    version_w = max(max(len(c.version) for c in containers), 9) + 11
    status_w = 25

    header = (
        f"{C.BOLD}{C.CYAN}{'CONTAINER':<{name_w}}{'IMAGE':<{image_w}}"
        f"{'STATUS':<{status_w - 8}}{'VERSION':<{version_w - 9}}UPDATE AVAILABLE{C.RESET}"
    )
    print(header)
    print(f"{C.GRAY}{'-' * min(width, name_w + image_w + status_w + version_w + 20)}{C.RESET}")

    tot = 0
    uas = 0
    run = 0
    sto = 0

    for c in containers:
        name = c.name
        image = c.image
        status = c.state
        ports = c.ports
        version = c.version
        update = c.update_status
        tot += 1
        if update['update_available']:
            uas += 1
        if status == 'running':
            run += 1
        if status == 'exited':
            sto += 1
        print(
            f"{C.BOLD}{name:<{name_w}}{C.RESET}"
            f"{C.DIM}{image:<{image_w}}{C.RESET}"
            f"{color_state(status):<{status_w}}"
            f"{color_version(version):<{version_w}}"
            f"{color_update(update)}"
        )
    print()
    run_color = C.GREEN
    if run == 0:
        run_color = C.RED
    sto_color = C.RED
    if sto == 0:
        sto_color = C.GRAY

    print(
        f"{C.BOLD}{tot}{C.RESET} containers configured "
        f"{run_color}{run}{C.RESET} containers running and "
        f"{sto_color}{sto}{C.RESET} containers stopped. "
        f"{C.YELLOW}{uas}{C.RESET} containers with update available"
    )
    print()

def cli_format_host(host):
    """Pretty-print containers in a table with color and emojis."""
    print(f"{C.BOLD}Docker host: {C.RED}{host.name}{C.RESET}\n")

def json_format(hosts):
    out = [host.as_dict() for host in hosts.values() if len(host.containers) > 0]
    if out:
        print(json.dumps(out))
    else:
        print(json.dumps({"message": "No containers matching the filter found"}))

class Host:
    """Simple class for host data."""

    def __init__(self, host: dict) -> None:
        self.id = host.get('id')
        self.name = host.get('name')
        self._containers = []
        self.container_order = 'name'  # 'name' 'image' 'update_available'

    def add_container(self, container: "Container"):
        self._containers.append(container)
        container.host = self

    @property
    def containers(self):
        if self.container_order == 'image':
            return sorted(self._containers, key=lambda c: c.image)
        if self.container_order == 'state':
            return sorted(self._containers, key=lambda c: c.state)
        if self.container_order == 'update_available':
            return sorted(self._containers, key=lambda c: c.update_available)
        return sorted(self._containers, key=lambda c: c.name)

    @containers.setter
    def containers(self, containers):
        for c in containers:
            self.add_container(c)

    def updates_available(self):
        return [c for c in self.containers if c.update_available]

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "containers": [c.as_dict() for c in self.containers],
        }
    def as_summary_dict(self):
        return {
            "id": self.id,
            "name": self.name,
        }


    def __repr__(self):
        return f"{self.id}: {self.name}"


class Container:
    """Simple class for container data."""

    def __init__(self, cont: dict) -> None:
        self.id = cont.get('id')
        self.name = cont.get('name')
        self.host_name = cont.get('host_name')
        self.host_id = cont.get('host_id')
        self.host = None
        self.image = cont.get('image')
        self.state = cont.get('state')
        self.ports = cont.get('ports', "")
        self.container_id = f"{cont.get('host_id')}:{self.id}"
        self.created = self.parse_ns_iso8601(cont.get('created'))
        self.started = self.parse_ns_iso8601(cont.get('created'))
        self.healthy = cont.get('healthy')
        self._update_status = { 'update_available': False }
        self._version = self._get_version(cont)

    @property
    def version(self):
        return self._version or "N/A"
    @property
    def update_available(self):
        return self._update_status['update_available']

    @update_available.setter
    def update_available(self, update_available: bool):
        self._update_status['update_available'] = bool(update_available)

    @property
    def update_status(self):
        return self._update_status

    @update_status.setter
    def update_status(self, update_status: dict):
        self._update_status = update_status
        if not self._update_status['current_version'] and self._version:
            self._update_status['current_version'] = self._version
        if self._update_status.get('last_checked_at'):
            self._update_status['last_checked_at'] = self.parse_ns_iso8601(self._update_status.get('last_checked_at'))
            self._update_status['last_checked'] = self.human_time_diff(self._update_status['last_checked_at']).replace("since", "").replace("for ", "") + " ago"

    def update_status_dict(self):
        ret = self._update_status
        if self._update_status.get('last_checked_at'):
            ret['last_checked_at'] = self._update_status.get('last_checked_at').strftime("%Y-%m-%d %H:%M:%S")
        return ret


    def as_dict(self):
        ret = {
            "id": self.id,
            "container_id": self.container_id,
            "name": self.name,
            "host": self.host.as_summary_dict(),
            "update_status": self.update_status_dict(),
            "version": self.version,
            "state": self.state,
            "ports": self.ports,
            "image": self.image,
            "created": self.created.strftime("%Y-%m-%d %H:%M:%S"),
            "started": self.started.strftime("%Y-%m-%d %H:%M:%S"),
            "running_for": self.human_time_diff(self.started)
        }
        return ret


    def _get_version(self, container: dict) -> str:
        version = container.get('labels').get('org.opencontainers.image.version')
        image_name = container.get('image').split(":", 1)[0].split("/")[-1]
        image_version = container.get('image').split(":", 1)[1]

        if not version:
            version_env_strings = ['PG_VERSION', 'REDIS_VERSION', 'INFLUXDB_VERSION']
            for env in container['env']:
                if env in version_env_strings:
                    version = container['env'][env]

        if not version:
            if image_name == 'php':
                for env in container['env']:
                    if env == 'PHP_VERSION':
                        version = container['env'][env]

        if not version:
            if image_name == 'nginx':
                for env in container['env']:
                    if env == 'NGINX_VERSION':
                        version = container['env'][env]

        if not version:
            if image_name == 'python':
                for env in container['env']:
                    if env == 'PYTHON_VERSION':
                        version = container['env'][env]
        return version

    def parse_ns_iso8601(self, s: str) -> datetime:
        try:
            s = s.rstrip("Z")
            if "." in s:
                ts, frac = s.split(".")
                frac = frac[:6]
                s = f"{ts}.{frac}"
            return datetime.fromisoformat(s)
        except (ValueError, AttributeError):
            return datetime.now()

    def human_time_diff(self, past: datetime, now: datetime | None = None) -> str:
        """
        Returns a nice human-readable difference between a past datetime and now.
        Example outputs:
          - "just now"
          - "5 seconds ago"
          - "2 minutes ago"
          - "3 hours ago"
          - "yesterday"
          - "5 days ago"
          - "3 weeks ago"
          - "2 months ago"
          - "1 year ago"
          - "in 5 minutes" (future)
        """
        if now is None:
            now = datetime.now()

        delta = now - past
        seconds = int(delta.total_seconds())

        if seconds < 0:
            return self.human_time_diff_future(-seconds)

        # Now in "seconds ago"
        if seconds < 60:
            return f"for {seconds} seconds"

        minutes = seconds // 60
        if minutes < 60:
            return "for 1 minute" if minutes == 1 else f"for {minutes} minutes"

        hours = minutes // 60
        if hours < 24:
            return "for 1 hour" if hours == 1 else f"for {hours} hours"

        days = hours // 24
        if days == 1:
            return "since yesterday"
        if days < 7:
            return f"for {days} days"

        weeks = days // 7
        if weeks < 5:
            return "for 1 week" if weeks == 1 else f"for {weeks} weeks"

        months = days // 30
        if months < 12:
            return "for 1 month" if months == 1 else f"for {months} months"

        years = days // 365
        return "for 1 year" if years == 1 else f"for {years} years"

    def human_time_diff_future(self, seconds: int) -> str:
        """Helper for future timestamps."""
        if seconds < 60:
            return f"in {seconds} seconds"

        minutes = seconds // 60
        if minutes < 60:
            return "in 1 minute" if minutes == 1 else f"in {minutes} minutes"

        hours = minutes // 60
        if hours < 24:
            return "in 1 hour" if hours == 1 else f"in {hours} hours"

        days = hours // 24
        if days < 7:
            return "tomorrow" if days == 1 else f"in {days} days"

        weeks = days // 7
        if weeks < 5:
            return "in 1 week" if weeks == 1 else f"in {weeks} weeks"

        months = days // 30
        if months < 12:
            return "in 1 month" if months == 1 else f"in {months} months"

        years = days // 365
        return "in 1 year" if years == 1 else f"in {years} years"


    def __repr__(self):
        return f"{self.id}: {self.name}@{self.host.name}"

class APIClient:
    """Simple API client with Bearer token authentication."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers = {'Authorization': f"Bearer {api_key}" }

    def get(self, path: str, **kwargs):
        """GET request to an API endpoint."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        r = self.session.get(url, **kwargs)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, query=None, data=None, json=None, **kwargs):
        """POST request to an API endpoint."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        r = self.session.post(url, params=query, data=data, json=json, **kwargs)
        r.raise_for_status()
        return r.json()


def _container_match(container: Container, name_match: str, image_match: str) -> bool:
    partial_names = ['www', 'php', 'librenms']
    if not name_match and not image_match:
        return True
    elif name_match and image_match:
        if image_match in container.image:
            if name_match == container.name:
                return True
            if name_match in partial_names and name_match in container.name:
                return True
    elif name_match and not image_match:
        if name_match == container.name:
            return True
        if name_match in partial_names and name_match in container.name:
            return True
    elif image_match and not name_match:
        if image_match in container.image:
            return True
    return False


def get_container_status(client, args) -> dict:
    hosts = {}
    data = client.get("hosts")
    for host in data:
        if not args.host or host['name'] == args.host:
            hosts[host.get('id')] = Host(host)
            hosts[host.get('id')].container_order = args.order

    updates = client.get("updates/summary")
    data = client.get("containers")
    for c in data:
        container = Container(c)
        if container.host_id in hosts:
            if _container_match(container, args.container, args.image):
                if container.container_id in updates.get('containers_with_updates', []):
                    update_status = client.get(f"hosts/{container.host_id}/containers/{container.id}/update-status")
                    container.update_status = update_status

                if args.updates_only and not container.update_available:
                    continue
                hosts[container.host_id].add_container(container)
    return hosts

def check_updates(client, host_id: str | None = None, container_id: str | None = None) -> None:
    if host_id and container_id:
        client.post(f"hosts/{host_id}/containers/{container_id}/check-update")
    else:
        client.post("updates/check-all")

def execute_update(client, host_id: str, container_id: str, quiet: bool = False) -> None:
    query = { "force": True }
    try:
        result = client.post(f"hosts/{host_id}/containers/{container_id}/execute-update", query=query)
    except requests.exceptions.HTTPError as e:
        error = e.response.json()
        if error['detail'] == 'No update available for this container':
            if not quiet:
                print(f"✅ {error['detail']}")
        else:
            if not quiet:
                print(f"❌ HTTP exception: {error['detail']}")
        return error
    else:
        if result['status'] == 'success':
            if not quiet:
                print(f"✅ {result['message']}")
        else:
            if not quiet:
                print(f"❌ {result['message']}")
        return result

def execute_restart(client, host_id: str, container_id: str, quiet: bool = False) -> None:
    try:
        result = client.post(f"/hosts/{host_id}/containers/{container_id}/restart")
    except requests.exceptions.HTTPError as e:
        error = e.response.json()
        if not quiet:
            print(f"❌ {error}")
        return error
    else:
        if result['status'] == 'success':
            if not quiet:
                print(f"✅ {result['message']}")
        else:
            if not quiet:
                print(f"❌ {result['message']}")
        return result



def main():
    parser = argparse.ArgumentParser(
        description="CLI tool for monitoring Docker containers via a dockmon API server.",
        conflict_handler="resolve",
    )
    parser.add_argument("-h", "--host", help="Limit to host.")
    parser.add_argument("-c", "--container", help="Limit to container name.")
    parser.add_argument("-i", "--image", help="Limit to image name.")
    parser.add_argument("-u", "--updates-only", action="store_true", help="Only containers with updates.")
    parser.add_argument("-o", "--order", choices=['name', 'image', 'state', 'update_available'], default='name', help="Container sort order")
    parser.add_argument("-j", "--json", action="store_true", help="JSON output.")
    parser.add_argument("--check-updates", action="store_true", help="Check for updates")
    parser.add_argument("--update", "--upgrade", action="store_true", help="Update containers")
    parser.add_argument("--restart", "--reboot", action="store_true", help="Restart containers")

    args = parser.parse_args()

    api_url, api_key = resolve_credentials()
    client = APIClient(api_url, api_key)

    if args.check_updates and not args.host and not args.container:
        check_updates(client)

    elif args.check_updates:
        hosts = get_container_status(client, args)
        for host in hosts.values():
            for container in host.containers:
                if not args.json:
                    print(f"Checking update for host {host.name} - {host.id} container {container.name} - {container.id}")
                check_updates(client, host.id, container.id)

    elif args.update:
        hosts = get_container_status(client, args)
        for host in hosts.values():
            for container in host.containers:
                if not args.json:
                    print(f"⬆️  Executing update for container {container.name} on {host.name}")
                result = execute_update(client, host.id, container.id, quiet=args.json)
                if args.json:
                    print(json.dumps(result, indent=4, sort_keys=True))
                    sys.exit()

    elif args.restart:
        hosts = get_container_status(client, args)
        for host in hosts.values():
            for container in host.containers:
                if not args.json:
                    print(f"♻️  Restarting container {container.name} on {host.name}")
                result = execute_restart(client, host.id, container.id, quiet=args.json)
                if args.json:
                    print(json.dumps(result, indent=4, sort_keys=True))
                    sys.exit()

    else:
        hosts = get_container_status(client, args)

        if args.json:
            json_format(hosts)
        else:
            for host in hosts:
                cli_format_host(hosts[host])
                cli_format_containers(hosts[host].containers)


if __name__ == "__main__":
    main()

