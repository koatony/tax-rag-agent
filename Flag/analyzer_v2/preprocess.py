# 輸入正規化器：同時接受舊版扁平格式與新版上傳格式。

import json


def preprocess(raw: dict) -> dict:
    # 接受兩種輸入格式：
    #   (a) 舊版扁平格式 — {client, tax_year, expenses, ...}
    #   (b) 新版上傳格式 — {taxpayer_profile: {...}, uploaded_documents: [...]}
    # 回傳一份正規化後、可直接餵給 PLANNER prompt 的 dict。
    # 為什麼：系統同時要支援舊版（前端直接送扁平 client/tax_year/expenses）
    # 和新版上傳格式（taxpayer_profile + uploaded_documents，且 content 是
    # 字串化的 JSON），如果不集中在這裡統一轉換，PLANNER/MAP 的 prompt
    # 組裝邏輯和後面的 safety_nets 檢查就要各自處理兩種格式，容易出錯又
    # 難維護；所有下游程式碼只需要認得這裡輸出的單一正規化格式。
    if "taxpayer_profile" not in raw:
        return raw  # already legacy format

    profile = raw["taxpayer_profile"]
    docs_raw = raw.get("uploaded_documents", [])

    # Parse stringified content fields
    documents = []
    for doc in docs_raw:
        entry = {"file_name": doc.get("file_name", "")}
        content = doc.get("content", "")
        if isinstance(content, str):
            try:
                entry["content"] = json.loads(content)
            except json.JSONDecodeError:
                entry["content"] = content  # leave as string if unparseable
        else:
            entry["content"] = content
        documents.append(entry)

    return {
        "client": profile.get("Name", "N/A"),
        "tax_year": profile.get("Tax Year", "N/A"),
        "filing_status": profile.get("Filing Status", ""),
        "state": profile.get("State", ""),
        "uploaded_documents": documents,
    }
