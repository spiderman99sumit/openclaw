#!/usr/bin/env python3
"""Google Drive + Sheets helper for the AI Influencer Factory.

Phase 1 responsibilities:
- bootstrap_job_drive(job_id)
- upload_preview_to_drive(job_id, file_path, metadata)
- record_asset_in_sheet(...)
- update_job_row(...)

Auth model:
- Uses service account JSON at /kaggle/working/.openclaw/credentials/sa-gdrive.json
- Drive root folder + Sheet ID default from docs/FACTORY_BLUEPRINT.md

Dependencies:
    pip install google-api-python-client google-auth google-auth-httplib2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except Exception as e:  # pragma: no cover
    print(
        "Missing Google API dependencies. Install with: "
        "pip install google-api-python-client google-auth google-auth-httplib2",
        file=sys.stderr,
    )
    raise

WORKSPACE = Path("/kaggle/working/.openclaw/workspace")
CREDENTIALS_PATH = Path("/kaggle/working/.openclaw/credentials/sa-gdrive.json")
DEFAULT_SHEET_ID = "1Mb_XYkrwjwNPACMN-nMRbUpmXZ_uKaQ8SoyQFueyGbM"
DEFAULT_DRIVE_ROOT_ID = "1v4Kc4c5dYeTQF2MVpIoac3hzt0WFJrnI"

JOB_SUBFOLDERS = [
    "intake",
    "references",
    "dataset",
    "previews",
    "approvals",
    "lora",
    "final_batches",
    "delivery",
    "logs",
    "metadata",
]

JOBS_HEADERS = [
    "job_id","client_name","platform","package","niche","persona_name","status","priority",
    "deadline","drive_job_folder","local_job_folder","reference_count","dataset_ready",
    "preview_folder","preview_contact_sheet","preview_approved","training_platform","lora_name",
    "lora_version","lora_status","workflow_name","prompt_pack_version","final_folder",
    "approved_count","delivery_folder","qa_status","notes","last_updated"
]
RUNS_HEADERS = [
    "run_id","job_id","stage","worker_platform","workflow_name","model_name","lora_name",
    "seed","width","height","prompt_hash","negative_hash","input_count","output_count","status",
    "start_time","end_time","log_path","artifact_path","notes"
]
ASSETS_HEADERS = [
    "asset_id","job_id","stage","asset_type","file_name","file_path","drive_link",
    "approved","selected_for_delivery","created_at","notes"
]


@dataclass
class FactoryGoogleClient:
    drive: Any
    sheets: Any
    sheet_id: str
    drive_root_id: str

    @classmethod
    def create(
        cls,
        credentials_path: Path = CREDENTIALS_PATH,
        sheet_id: str = DEFAULT_SHEET_ID,
        drive_root_id: str = DEFAULT_DRIVE_ROOT_ID,
    ) -> "FactoryGoogleClient":
        scopes = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]
        creds = service_account.Credentials.from_service_account_file(
            str(credentials_path), scopes=scopes
        )
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return cls(drive=drive, sheets=sheets, sheet_id=sheet_id, drive_root_id=drive_root_id)

    def ensure_sheet_headers(self) -> None:
        existing = self.sheets.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
        titles = {s["properties"]["title"] for s in existing.get("sheets", [])}
        wanted = {
            "Jobs": JOBS_HEADERS,
            "Runs": RUNS_HEADERS,
            "Assets": ASSETS_HEADERS,
        }
        requests = []
        for title in wanted:
            if title not in titles:
                requests.append({"addSheet": {"properties": {"title": title}}})
        if requests:
            self.sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id, body={"requests": requests}
            ).execute()
        for title, headers in wanted.items():
            self.sheets.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{title}!A1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()

    def find_folder(self, name: str, parent_id: str) -> Optional[Dict[str, str]]:
        q = (
            f"name = '{name.replace("'", "\\'")}' and "
            f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        res = self.drive.files().list(q=q, fields="files(id,name,webViewLink)", pageSize=10).execute()
        files = res.get("files", [])
        return files[0] if files else None

    def ensure_folder(self, name: str, parent_id: str) -> Dict[str, str]:
        existing = self.find_folder(name, parent_id)
        if existing:
            return existing
        body = {
            "name": name,
            "parents": [parent_id],
            "mimeType": "application/vnd.google-apps.folder",
        }
        return self.drive.files().create(body=body, fields="id,name,webViewLink").execute()

    def bootstrap_job_drive(self, job_id: str, folder_name: Optional[str] = None) -> Dict[str, Any]:
        job_folder = self.ensure_folder(folder_name or job_id, self.drive_root_id)
        subfolders: Dict[str, Dict[str, str]] = {}
        for sub in JOB_SUBFOLDERS:
            subfolders[sub] = self.ensure_folder(sub, job_folder["id"])
        return {"job_id": job_id, "job_folder": job_folder, "subfolders": subfolders}

    def upload_file(self, local_path: Path, parent_id: str, remote_name: Optional[str] = None) -> Dict[str, str]:
        local_path = local_path.resolve()
        mime, _ = mimetypes.guess_type(str(local_path))
        media = MediaFileUpload(str(local_path), mimetype=mime or "application/octet-stream", resumable=False)
        body = {"name": remote_name or local_path.name, "parents": [parent_id]}
        return self.drive.files().create(
            body=body,
            media_body=media,
            fields="id,name,webViewLink,webContentLink,mimeType",
        ).execute()

    def get_sheet_rows(self, tab: str) -> List[List[str]]:
        res = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.sheet_id,
            range=f"{tab}!A:ZZ",
        ).execute()
        return res.get("values", [])

    def _row_map(self, headers: List[str], data: Dict[str, Any]) -> List[Any]:
        return [data.get(h, "") for h in headers]

    def upsert_row(self, tab: str, headers: List[str], key_field: str, data: Dict[str, Any]) -> str:
        rows = self.get_sheet_rows(tab)
        if not rows:
            self.sheets.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{tab}!A1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()
            rows = [headers]
        sheet_headers = rows[0]
        key_idx = sheet_headers.index(key_field)
        target_key = str(data.get(key_field, ""))
        row_values = self._row_map(sheet_headers, data)
        for idx, row in enumerate(rows[1:], start=2):
            value = row[key_idx] if key_idx < len(row) else ""
            if value == target_key:
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{tab}!A{idx}",
                    valueInputOption="RAW",
                    body={"values": [row_values]},
                ).execute()
                return f"updated:{idx}"
        self.sheets.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=f"{tab}!A:ZZ",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row_values]},
        ).execute()
        return "inserted"

    def update_job_row(self, job_data: Dict[str, Any]) -> str:
        return self.upsert_row("Jobs", JOBS_HEADERS, "job_id", job_data)

    def record_asset_row(self, asset_data: Dict[str, Any]) -> str:
        return self.upsert_row("Assets", ASSETS_HEADERS, "asset_id", asset_data)


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def job_dir(job_id: str) -> Path:
    return WORKSPACE / "jobs" / job_id


def bootstrap_local_job(job_id: str) -> Dict[str, Any]:
    base = job_dir(job_id)
    base.mkdir(parents=True, exist_ok=True)
    for sub in JOB_SUBFOLDERS:
        (base / sub).mkdir(parents=True, exist_ok=True)
    metadata_dir = base / "metadata"
    assets_path = metadata_dir / "assets.json"
    if not assets_path.exists():
        save_json(assets_path, [])
    job_json_path = metadata_dir / "job.json"
    if not job_json_path.exists():
        save_json(
            job_json_path,
            {
                "job_id": job_id,
                "status": "preview_running",
                "local_job_folder": str(base),
                "last_updated": now_iso(),
            },
        )
    return {"job_dir": str(base), "assets_path": str(assets_path), "job_json_path": str(job_json_path)}


def bootstrap_job_drive(client: FactoryGoogleClient, job_id: str, folder_name: Optional[str] = None) -> Dict[str, Any]:
    local = bootstrap_local_job(job_id)
    drive_data = client.bootstrap_job_drive(job_id, folder_name=folder_name)
    preview_folder = drive_data["subfolders"]["previews"]
    final_folder = drive_data["subfolders"]["final_batches"]
    delivery_folder = drive_data["subfolders"]["delivery"]
    job_record = load_json(Path(local["job_json_path"]), {})
    job_record.update(
        {
            "job_id": job_id,
            "status": job_record.get("status", "preview_running"),
            "drive_job_folder": drive_data["job_folder"]["webViewLink"],
            "local_job_folder": local["job_dir"],
            "preview_folder": preview_folder["webViewLink"],
            "final_folder": final_folder["webViewLink"],
            "delivery_folder": delivery_folder["webViewLink"],
            "last_updated": now_iso(),
        }
    )
    save_json(Path(local["job_json_path"]), job_record)
    sheet_result = client.update_job_row(job_record)
    return {"local": local, "drive": drive_data, "sheet": sheet_result}


def upload_preview_to_drive(
    client: FactoryGoogleClient,
    job_id: str,
    file_path: Path,
    *,
    asset_id: Optional[str] = None,
    notes: str = "",
    file_name: Optional[str] = None,
    folder_name: Optional[str] = None,
) -> Dict[str, Any]:
    file_path = file_path.resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    drive_data = client.bootstrap_job_drive(job_id, folder_name=folder_name)
    preview_folder = drive_data["subfolders"]["previews"]
    uploaded = client.upload_file(file_path, preview_folder["id"], remote_name=file_name)

    asset_id = asset_id or f"{job_id}:{file_path.stem}"
    asset = {
        "asset_id": asset_id,
        "job_id": job_id,
        "stage": "preview",
        "asset_type": "image",
        "file_name": uploaded["name"],
        "file_path": str(file_path),
        "drive_link": uploaded.get("webViewLink", ""),
        "approved": False,
        "selected_for_delivery": False,
        "created_at": now_iso(),
        "notes": notes,
    }
    sheet_result = client.record_asset_row(asset)

    local_assets = Path(job_dir(job_id) / "metadata" / "assets.json")
    assets = load_json(local_assets, [])
    assets = [a for a in assets if a.get("asset_id") != asset_id] + [asset]
    save_json(local_assets, assets)

    job_json = Path(job_dir(job_id) / "metadata" / "job.json")
    job_record = load_json(job_json, {"job_id": job_id})
    job_record.update(
        {
            "job_id": job_id,
            "status": "preview_review",
            "preview_folder": preview_folder.get("webViewLink", ""),
            "last_updated": now_iso(),
        }
    )
    save_json(job_json, job_record)
    client.update_job_row(job_record)

    return {
        "uploaded": uploaded,
        "asset": asset,
        "sheet": sheet_result,
        "preview_folder": preview_folder,
    }


def update_job_status(
    client: FactoryGoogleClient,
    job_id: str,
    *,
    status: str,
    notes: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    path = job_dir(job_id) / "metadata" / "job.json"
    job_record = load_json(path, {"job_id": job_id})
    job_record["status"] = status
    job_record["last_updated"] = now_iso()
    if notes is not None:
        job_record["notes"] = notes
    if extra:
        job_record.update(extra)
    save_json(path, job_record)
    return client.update_job_row(job_record)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Factory Drive/Sheets helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bootstrap-job")
    b.add_argument("job_id")
    b.add_argument("--folder-name")
    b.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    b.add_argument("--drive-root-id", default=DEFAULT_DRIVE_ROOT_ID)

    u = sub.add_parser("upload-preview")
    u.add_argument("job_id")
    u.add_argument("file_path")
    u.add_argument("--asset-id")
    u.add_argument("--notes", default="")
    u.add_argument("--file-name")
    u.add_argument("--folder-name")
    u.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    u.add_argument("--drive-root-id", default=DEFAULT_DRIVE_ROOT_ID)

    j = sub.add_parser("update-job-status")
    j.add_argument("job_id")
    j.add_argument("status")
    j.add_argument("--notes")
    j.add_argument("--extra-json")
    j.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    j.add_argument("--drive-root-id", default=DEFAULT_DRIVE_ROOT_ID)

    return p


def main() -> int:
    args = build_parser().parse_args()
    client = FactoryGoogleClient.create(sheet_id=args.sheet_id, drive_root_id=args.drive_root_id)
    client.ensure_sheet_headers()

    if args.cmd == "bootstrap-job":
        result = bootstrap_job_drive(client, args.job_id, folder_name=args.folder_name)
    elif args.cmd == "upload-preview":
        result = upload_preview_to_drive(
            client,
            args.job_id,
            Path(args.file_path),
            asset_id=args.asset_id,
            notes=args.notes,
            file_name=args.file_name,
            folder_name=args.folder_name,
        )
    elif args.cmd == "update-job-status":
        extra = json.loads(args.extra_json) if args.extra_json else None
        result = update_job_status(client, args.job_id, status=args.status, notes=args.notes, extra=extra)
    else:  # pragma: no cover
        raise ValueError(args.cmd)

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
