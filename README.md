# Simple Chat Application (Computer Networks Term Project)

A multi-client networked chat application built in Python 3 using **raw TCP Socket Programming** (`socket`) and a **Tkinter GUI** (`tkinter`). Designed to run across separate physical computers over a Local Area Network (LAN) or a **Cloud VPS** (`B2`), with zero external Python packages required.

---

## Architecture Overview

- **Server (`server/` + `common/`):** Headless multi-threaded TCP server listening on `0.0.0.0:5000`. Can run inside **Docker** (locally on Docker Desktop or remotely on a Cloud VPS) or directly via Python 3.
- **Client (`client/` + `common/`):** Desktop `tkinter` GUI application that runs directly on each user's laptop/PC and connects to the Server IP (`127.0.0.1`, LAN IP, or Cloud VPS Public IP) over TCP port `5000`.
- **Wire Protocol:** Newline-delimited (`\n`) UTF-8 JSON packets with a 3-key envelope (`type`, `timestamp`, `payload`). See [`JsonFormat.md`](JsonFormat.md) for the full specification.

---

## 1. How to Run the Server

You can run the server using **Docker** (recommended for simulating a Cloud VPS on Docker Desktop or deploying to a Linux VPS) or directly with **Python 3**.

### Option A: Run with Docker Compose (Recommended)
Make sure **Docker Desktop** (Windows/macOS) or **Docker Engine** (Linux VPS) is running, then run from the project root:

```bash
# 1. Build and start the server in the background
docker compose up -d --build

# 2. View live server logs
docker compose logs -f

# 3. Stop the server
docker compose down
```

> **Optional — AI Summary Bonus (`B1`):**
> To pass a Gemini API key to the containerized server, run:
> ```bash
> GEMINI_API_KEY="your_api_key_here" docker compose up -d --build
> ```
> *(Or create a `.env` file in the project root with `GEMINI_API_KEY=your_api_key_here`.)*

---

### Option B: Run with `Dockerfile` Only (Without Compose)
If you prefer using standalone `docker` commands without `docker-compose.yml`:

```bash
# 1. Build the server image
docker build -t compnetwork-chat-server .

# 2. Run the container on port 5000
docker run -d \
  --name compnetwork-chat-server \
  --restart unless-stopped \
  -p 5000:5000 \
  -e GEMINI_API_KEY="your_api_key_here" \
  compnetwork-chat-server

# 3. View logs
docker logs -f compnetwork-chat-server
```

---

### Option C: Run Directly with Python 3 (No Docker)
Since the server uses only Python's standard library, you can run it directly with Python 3.10+:

```bash
python -m server.server --host 0.0.0.0 --port 5000
```

---

## 2. How to Connect Clients (`client/`)

> **Important:** Always run the Client directly on your host OS (not inside Docker) because it opens a desktop `tkinter` GUI window and accesses your computer's audio hardware.

```bash
python -m client.main
```

In the Login Window, enter the **Server IP** based on where the server is running:
1. **Same computer (Local / Docker Desktop simulation):** `127.0.0.1` (Port `5000`)
2. **Another teammate's laptop on the same Wi-Fi / LAN:** The host machine's LAN IP (e.g., `192.168.1.x`, Port `5000`)
3. **Cloud VPS (`B2`):** The VPS Public IPv4 address (e.g., `128.199.x.x`, Port `5000`)

---

## 3. Deploying the Server on a Cloud VPS (`Bonus B2`)

1. **Create an Ubuntu VPS** (e.g., DigitalOcean Droplet via GitHub Student Pack, Azure for Students, or GCP Compute Engine in Singapore region).
2. **Open TCP Port `5000`:**
   - In your Cloud Provider's Firewall / Security Group, allow inbound **TCP `5000`** from `0.0.0.0/0`.
   - On the Ubuntu VPS firewall (if enabled):
     ```bash
     sudo ufw allow 5000/tcp
     ```
3. **Install Docker & Start the Server on the VPS:**
   ```bash
   # Install Docker & Docker Compose plugin on Ubuntu
   sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git

   # Clone the repository and start the server container
   git clone <your-repo-url>
   cd CompNetwork
   sudo docker compose up -d --build

   # Check live server logs
   sudo docker compose logs -f
   ```

---

## 4. Running Automated Unit Tests

Run the full test suite from the project root:

```bash
python -m unittest discover -s tests -v
```
