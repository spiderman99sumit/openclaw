# Status Machine

## Valid Statuses
new
intake_ready
preview_running
preview_review
approved_for_training
training_running
training_done
final_generation_running
qa_review
delivery_ready
delivered
blocked
failed

## Transitions
new -> intake_ready
intake_ready -> preview_running
preview_running -> preview_review
preview_review -> approved_for_training | blocked
approved_for_training -> training_running
training_running -> training_done | failed
training_done -> final_generation_running
final_generation_running -> qa_review | failed
qa_review -> delivery_ready | blocked
delivery_ready -> delivered
any -> blocked
any -> failed
