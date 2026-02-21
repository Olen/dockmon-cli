# dockmon-cli

A command-line tool for monitoring Docker containers via a [dockmon](https://github.com/darthnorse/dockmon) API server.

## Installation

```bash
pip install git+https://github.com/Olen/dockmon-cli.git
```

## Configuration

`dockmon-cli` needs an API URL and key to connect to your dockmon server. Credentials are resolved in this order:

1. **Environment variables**
   ```bash
   export DOCKMON_API_URL=https://dockmon.example.com/api
   export DOCKMON_API_KEY=dockmon_yourkey
   ```

2. **Config file** (`~/.config/dockmon/config.ini`)
   ```ini
   [api]
   url = https://dockmon.example.com/api
   key = dockmon_yourkey
   ```

3. **Docker secrets** (`/run/secrets/dockmon_api_url` and `/run/secrets/dockmon_api_key`)

## Usage

```bash
# Show all containers across all hosts
dockmon-cli

# Filter by host
dockmon-cli -h myhost

# Filter by container name
dockmon-cli -c mycontainer

# Filter by image name
dockmon-cli -i nginx

# Show only containers with available updates
dockmon-cli -u

# JSON output
dockmon-cli -j

# Sort by image, state, or update status
dockmon-cli -o image
dockmon-cli -o state
dockmon-cli -o update_available

# Check for updates
dockmon-cli --check-updates

# Check updates for a specific container
dockmon-cli --check-updates -h myhost -c mycontainer

# Execute an update
dockmon-cli --update -h myhost -c mycontainer

# Restart a container
dockmon-cli --restart -h myhost -c mycontainer
```

## License

MIT
