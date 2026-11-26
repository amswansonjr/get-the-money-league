# Football preparation rehearsal

Manual, owner-only preparation for the existing League Headquarters website and Excel workbooks. This is not the weekly schedule or a publication workflow.

1. Sign in to the private football admin page and choose **Prepare Cloud Rehearsal**.
2. Open **Preparation Workflow**, select **Run Workflow** on `main`, and paste the Job ID.
3. When preparation finishes, review the private website preview and download both Excel review copies.

The workflow uses a standard GitHub-hosted Linux runner in this public repository. It has a 15-minute timeout, one-run concurrency, repository read permission and short-lived OIDC identity permission. The private admin verifies the repository ID, owner/actor ID, branch, workflow, event, run ID and exact queued commit before issuing a short-lived Microsoft access token. Microsoft refresh credentials stay encrypted in the private service.

Workbook bytes, collected inputs and outputs stay in the temporary runner workspace and private admin storage. No public artifacts, caches or private-data logs are created. The workbook updater works on downloaded copies; it does not replace the existing OneDrive files. Website and workbook candidate hashes are bound to one immutable review package. A successful rehearsal cannot publish, approve or deliver files.

Free-only guards stop on file/storage limits. No paid runner, storage upgrade or subscription is authorized. Scheduling and publication must be connected and rehearsed separately.

The `website` and `workbook` folders reuse the established local updater/exporter. Header edits and website template hashes preserve reviewed presentation changes; upstream template changes stop preparation for reconciliation. Missing projections produce the updater's explicit warnings rather than invented awards. Postseason processing remains outside this validated regular-season workflow.
