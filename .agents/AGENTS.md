# Rules

- **Infrastructure Deployment**: Never execute `terraform apply` directly. Wait for the user to execute it or use alternative CI/CD workflows as preferred by the user.

- **Milestone Tracking**: When user requests an update to the roadmap, the agent must:
    1. Read the `project_roadmap.md` file.
    2. Update the document to add the new milestone with the objective, design notes, architecture decisions and task list.
    3. Save the changes to the file.
    4. Confirm with the user that the roadmap has been updated.
    5. The agent should not execute any code or deploy any changes when updating the roadmap.

- **Artifact Storage**: When you need to save a working script (e.g. `format_mechanics.py`) or the results of an experiment (`mechanic_frequencies.json`), save it to the `scratch/` directory. Do not save generated artifacts to your workspace or working folders.

- **Testing**: Run unit tests before deploying any changes. For frontend changes, test the changes locally using the Jekyll server. 

- **Agentic Orchestration**: For all complex workspace tasks, reference the `Agentic Orchestrator` skill. Identify the appropriate specialized domains (BGG API, AWS Architecture, Site UI, Recommender System, or Data Engineering) required for the task, load their rules, and coordinate implementation sequentially. 

- **Docker Images**: Never build or push Docker images directly. Deployment processes and image builds should only be run via designated CI/CD pipelines (e.g. GitHub Actions).