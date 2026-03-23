import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.storage.database import init_db
from src.storage.repositories import ProviderConfigRepository

def run_test():
    init_db()
    repo = ProviderConfigRepository()
    
    # 1. Upsert a test provider
    provider_name = "test_selector_provider"
    repo.upsert(
        provider_name,
        url="https://test.com",
        icon="robot",
        new_chat_selector=".new-chat",
        input_selector="#input",
        send_button_selector="#send",
        reply_selector=".reply",
        dom_sample="<html><body>test DOM</body></html>"
    )
    print(f"Upserted provider: {provider_name}")
    
    # 2. Get and verify
    row = repo.get(provider_name)
    assert row is not None
    assert row.new_chat_selector == ".new-chat"
    assert row.reply_selector == ".reply"
    assert row.dom_sample == "<html><body>test DOM</body></html>"
    print("Verification of fields passed.")
    
    # 3. Update selectors
    repo.update_selectors(
        provider_name,
        reply_selector=".new-reply",
        dom_sample="<updated></updated>"
    )
    
    # 4. Verify update
    row2 = repo.get(provider_name)
    assert row2.new_chat_selector == ".new-chat" # Unchanged
    assert row2.reply_selector == ".new-reply" # Changed
    assert row2.dom_sample == "<updated></updated>"
    print("Verification of selective update passed.")

if __name__ == "__main__":
    run_test()
