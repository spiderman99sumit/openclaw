# Google Sheets Schema

## Tab: jobs
job_id,client_name,platform,package,niche,persona_name,status,priority,deadline,drive_job_folder,local_job_folder,reference_count,dataset_ready,preview_folder,preview_contact_sheet,preview_approved,training_platform,lora_name,lora_version,lora_status,workflow_name,prompt_pack_version,final_folder,approved_count,delivery_folder,qa_status,notes,last_updated

## Tab: runs
run_id,job_id,stage,worker_platform,workflow_name,model_name,lora_name,seed,width,height,prompt_hash,negative_hash,input_count,output_count,status,start_time,end_time,log_path,artifact_path,notes

## Tab: assets
asset_id,job_id,stage,asset_type,file_name,file_path,drive_link,approved,selected_for_delivery,created_at,notes

## Credential Names
- GOOGLE_SHEETS_CREDENTIAL_NAME = google_sheets_factory
- GOOGLE_DRIVE_CREDENTIAL_NAME = google_drive_factory
