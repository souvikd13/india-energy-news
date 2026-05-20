# India Energy News Digest

This repository publishes a daily India-focused energy news digest as a public GitHub Pages website.

It covers power, renewables, oil, gas, LNG, coal, grid, storage, hydrogen, DISCOMs, tariffs, and policy/regulatory news.

## Publish as a Public Link

1. Create a new GitHub repository, for example `india-energy-news`.
2. Upload all files from this folder to that repository.
3. In GitHub, open **Settings > Pages**.
4. Under **Build and deployment**, choose **GitHub Actions** as the source.
5. Open **Actions > Publish India Energy News**.
6. Click **Run workflow**.
7. After it completes, your public link will appear in the workflow deploy step and in **Settings > Pages**.

The link will look like:

```text
https://YOUR-USERNAME.github.io/india-energy-news/
```

## Daily Refresh

The workflow runs daily at `08:00 IST`.

You can change the schedule in `.github/workflows/publish.yml`.

## Email Sending

The site can also email the same digest when the workflow runs.

First edit `energy-news-config.json` and replace:

```json
"recipient@example.com"
```

with the predefined email address.

Then add these GitHub repository secrets in **Settings > Secrets and variables > Actions**:

- `SEND_EMAIL`: `true`
- `SMTP_SERVER`: for example `smtp.gmail.com`
- `SMTP_PORT`: usually `587`
- `SMTP_FROM`: sender email address
- `SMTP_USER`: SMTP login email/user
- `SMTP_PASSWORD`: SMTP password or app password

For Gmail, use an App Password.

## Local Test on a Machine With Python

```powershell
python generate_site.py
```

Then open:

```text
public/index.html
```

## Configure Sources

Edit `energy-news-config.json` to add or remove feeds, keywords, and exclude keywords.
