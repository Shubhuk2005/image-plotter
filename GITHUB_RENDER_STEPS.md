# GitHub And Render Step By Step

This file explains exactly how to:

1. upload this project to GitHub
2. deploy the backend on Render

This project is already prepared for Render:

- `index.html` is in the repo root
- `Dockerfile` is ready for hosted deployment
- `render.yaml` is in the repo root
- `backend.app:app` works with Gunicorn

## Part 1: Upload The Project To GitHub

### Option A: Create the repo from the GitHub website

1. Sign in to GitHub.
2. Click `New repository`.
3. Enter the repository name:

```text
image-plotter
```

4. Choose `Public` or `Private`.
5. Do not pre-add a `README`, `.gitignore`, or license if you want the cleanest first push.
6. Click `Create repository`.
7. Open a terminal in the project root.
8. Run these commands:

```bash
git init -b main
git add -A
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/image-plotter.git
git push -u origin main
```

### Option B: Create the repo with GitHub CLI

1. Open a terminal in the project root.
2. Run:

```bash
git init -b main
git add -A
git commit -m "Initial commit"
gh repo create image-plotter --public --source=. --remote=origin --push
```

### If the GitHub repo already exists and push is rejected

Sometimes GitHub already has a `README.md`, so the histories are different. Use this:

```bash
git remote add origin https://github.com/YOUR_USERNAME/image-plotter.git
git fetch origin main
git merge origin/main --allow-unrelated-histories
git push -u origin main
```

If Git asks you to fix a conflict:

1. open the conflicted file
2. keep the content you want
3. save the file
4. run:

```bash
git add -A
git commit
git push
```

## Part 2: Deploy The Backend On Render

This repo already contains `render.yaml`, so the easiest method is `Blueprint`.

### Render deploy steps

1. Sign in to Render.
2. Click `New`.
3. Click `Blueprint`.
4. Connect your GitHub account to Render if Render asks.
5. Select the repo:

```text
Shubhuk2005/image-plotter
```

6. Choose the `main` branch.
7. Render will detect the root `render.yaml`.
8. Review the service values:

```text
type: web
name: image-plotter
runtime: docker
plan: free
region: singapore
healthCheckPath: /api/health
```

9. Click `Apply`.
10. Wait for the build and deploy to finish.
11. Open the Render service URL.
12. Test these URLs:

```text
https://YOUR-SERVICE.onrender.com/
https://YOUR-SERVICE.onrender.com/api/health
```

If deployment succeeds, `/api/health` should return JSON like this:

```json
{
  "status": "ok",
  "stl_support": true
}
```

### Manual Render fallback

If you do not want to use `Blueprint`, you can create the service manually:

1. In Render, click `New`.
2. Click `Web Service`.
3. Select `Git Provider`.
4. Connect GitHub and choose `Shubhuk2005/image-plotter`.
5. Set the branch to `main`.
6. Choose the `Docker` runtime.
7. Render will use the root `Dockerfile`.
8. Set the health check path to:

```text
/api/health
```

9. Click `Create Web Service`.

## Part 3: Why This Repo Can Now Run On Render

I made these deployment changes:

1. `backend/app.py`
   - supports package imports for `backend.app:app`
   - still supports direct local run with `python backend/app.py`
2. `backend/__init__.py`
   - marks `backend` as a package
3. `Dockerfile`
   - uses Render's port with `${PORT:-5000}`
4. `render.yaml`
   - tells Render how to create the web service

## Part 4: Common Problems

### GitHub push rejected

Run:

```bash
git fetch origin main
git merge origin/main
git push
```

### Render deploy fails with port error

The app must listen on `0.0.0.0` and the host port. This repo already does that in `Dockerfile`.

### Render free service sleeps

Render free web services can spin down after inactivity. The first request after sleeping can be slow.

### Need logs on Render

Open the service in Render and check:

```text
Events
Logs
```

## Part 5: The Exact Repo Used Here

```text
https://github.com/Shubhuk2005/image-plotter
```

## References

- GitHub Docs: https://docs.github.com/en/github/importing-your-projects-to-github/adding-an-existing-project-to-github-using-the-command-line
- Render Blueprints: https://render.com/docs/blueprint-spec
- Render Web Services: https://render.com/docs/web-services
- Render Free Deploys: https://render.com/docs/free
