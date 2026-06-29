# ✈️ travel-assistant-system

Welcome to the **travel-assistant-system**! This project is a comprehensive intelligent travel booking platform that combines a traditional web application frontend with a powerful Cognitive Agent Engine backend.

## 🌟 Project Overview

The project is structured into two main components:

1. **🌐 Website (ASP.NET Core MVC):** The user-facing application where customers can browse, plan, and book their travel. It features modern MVC architecture to deliver dynamic content seamlessly.
2. **🧠 Cognitive Agent Engine (Python/LangGraph):** A multi-agent AI system utilizing large language models (LLMs) from OpenAI and Anthropic. It performs complex travel planning, interacts with APIs through MCP (Model Context Protocol) tool calling, processes documents/images, and serves intelligent insights back to the web interface.

## 📂 Project Structure

- `/website` - Contains the ASP.NET Core MVC source code.
- `/agent` - Contains the LangGraph-based AI agent engine, Docker configurations, and multi-agent workflow definitions.
- `.gitignore` - Root configuration to ignore build artifacts for both Python/AI and .NET ecosystems.

## 🚀 How to Run the Source Code

To get the entire system up and running, follow the instructions below for each respective component.

### 🌐 Running the Website

The website is built with .NET. Ensure you have the [.NET SDK](https://dotnet.microsoft.com/download) installed.

```bash
# Navigate to the website directory
cd website

# Restore dependencies
dotnet restore

# Run the ASP.NET Core application
dotnet run
```

The web application will typically start and listen on standard local ports (e.g., `http://localhost:5000` or `https://localhost:5001`).

### 🧠 Running the Agent Engine

The agent uses Docker and Docker Compose to spin up the required services, databases, and the LangGraph API.

```bash
# Navigate to the agent directory
cd agent

# Build and start the containerized services in detached mode
docker-compose up --build -d

# To view logs and ensure everything started correctly
docker-compose logs -f
```

*(Note: Don't forget to configure your `.env` file inside the `/agent` directory with the required API keys before running the Docker containers.)*
