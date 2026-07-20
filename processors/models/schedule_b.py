# =====================================================================
# REVIEW 重點 1: 金融與非金融領域之「精確度防禦」 (Precision Defense)
# =====================================================================
# 【為什麼一定要用 Decimal 運算，而非 float？】
# 1. 浮點數精度損失（Floating-Point Precision Loss）：在電腦底層中，二進制浮點數無法精確表示
#    十進位的小數（例如 0.1 + 0.2 在 float 計算下會得到 0.30000000000000004）。
# 2. 如果系統涉及計費（Billing）、購物車金額結算、點數折抵、甚至統計報表，累積誤差會造成帳目不對。
# 3. 解決方案：Python 中的 `Decimal` 類別能精確模擬人類的手算十進位。
# 4. ⚠️ 坑點：直接寫 `Decimal(0.1)` 仍然是錯的，因為 0.1 已經先被 Python 解析為不精確的 float。
#    必須寫成字串形式 `Decimal("0.1")`，這也是本檔案中 `Decimal(str(...))` 轉換的原理。
# =====================================================================
# REVIEW 重點 2: 三層式資料模型架構 (Three-Layer Data Model Architecture)
# =====================================================================
# 【本檔案 (models/schedule_b.py) 與 Layer 的對應關係】
# 1. 本檔案定義的 Model 實際上涵蓋了 Layer 1 (原始輸入模型) 與 Layer 3 (表面結果模型)，而非 Layer 2：
#    - Layer 1 (原始輸入模型)：
#      * 包含 `ScheduleBInputsV1`、`InterestItemV1`、`DividendItemV1`、`MarketDiscountItemV1`、`Form8815V1`、`SpecialCaseFlagsBV1` 等。
#      * 角色：吃 LLM 輸出的原始 Dict/JSON 結果，進行「強型別化」(e.g. 轉為 Decimal、對齊欄位名稱與處理預設值)，
#        產生各類型的強型別輸入物件，準備給核心計算引擎使用。
#    - Layer 2 (正規化與中間計算)：
#      * 角色：執行核心商業邏輯、金額合計、錯誤驗證、券商/付款人聚合。
#      * 實作位置：`processors/calculators/schedule_b.py` 與 `processors/validators/schedule_b.py` 中。
#    - Layer 3 (Schedule B 表面欄位)：
#      * 包含 `ScheduleBResultV1` 結構體。
#      * 角色：表示最後要填入 IRS 實體表單 Line 1 到 Line 8 的表面欄位、阻斷錯誤代碼及可否申報的元數據。
# =====================================================================

import json
import os
from decimal import Decimal
from typing import Dict, Any, List, Optional

class InterestItemV1:
    """
    [Layer 1] 利息項目模型 (Interest Item Model)
    
    代表單筆利息收入紀錄（通常來自 Form 1099-INT 或券商綜合對帳單 Substitute Statement）。
    """
    def __init__(self, **kwargs):
        """
        初始化利息項目，並進行強型別轉換與欄位對齊。
        """
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_statement_id = kwargs.get("source_statement_id")
        self.statement_issuer_name = kwargs.get("statement_issuer_name")
        self.source_document_type = kwargs.get("source_document_type")  # e.g., '1099-INT', 'SUBSTITUTE_STATEMENT'
        self.source_box = kwargs.get("source_box")
        self.payer_name = kwargs.get("payer_name")
        
        # 付款人申報金額處理 (對齊不同命名來源: payer_reported_amount, reported_amount, amount)
        amt_val = kwargs.get("payer_reported_amount") if kwargs.get("payer_reported_amount") is not None else kwargs.get("reported_amount") if kwargs.get("reported_amount") is not None else kwargs.get("amount")
        # 實踐精確度防禦：將數值轉成字串後再載入成 Decimal，避免浮點數誤差
        self.payer_reported_amount = Decimal(str(amt_val)) if amt_val is not None else Decimal("0.00")
        
        # 稅務特徵分類 (TAXABLE_INTEREST 應稅利息 vs TAX_EXEMPT_INTEREST 免稅利息)
        self.tax_character = kwargs.get("tax_character")
        if self.tax_character not in ("TAXABLE_INTEREST", "TAX_EXEMPT_INTEREST"):
            self.tax_character = "UNKNOWN"
                
        # 填表所需的特殊欄位與調整項目
        self.is_series_ee_or_i_interest = bool(kwargs.get("is_series_ee_or_i_interest", False))

    def to_dict(self) -> Dict[str, Any]:
        """
        將物件序列化成 Python dict 格式。
        因為標準 json 函式庫不支援 Decimal，故序列化時轉回 float。
        """
        return {
            "item_id": self.item_id,
            "source_statement_id": self.source_statement_id,
            "statement_issuer_name": self.statement_issuer_name,
            "source_document_type": self.source_document_type,
            "source_box": self.source_box,
            "payer_name": self.payer_name,
            "payer_reported_amount": float(self.payer_reported_amount),
            "reported_amount": float(self.payer_reported_amount),
            "tax_character": self.tax_character,
            "is_series_ee_or_i_interest": self.is_series_ee_or_i_interest,
        }

class DividendItemV1:
    """
    [Layer 1] 股利項目模型 (Dividend Item Model)
    
    代表單筆股利收入紀錄（通常來自 Form 1099-DIV 或券商綜合對帳單）。
    """
    def __init__(self, **kwargs):
        """
        初始化股利項目，並將金額欄位轉換為 Decimal 型別以確保精度。
        """
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_statement_id = kwargs.get("source_statement_id")
        self.statement_issuer_name = kwargs.get("statement_issuer_name")
        self.source_document_type = kwargs.get("source_document_type")  # e.g., '1099-DIV', 'SUBSTITUTE_STATEMENT'
        self.payer_name = kwargs.get("payer_name")
        
        # 普通股利金額 (對應 1099-DIV Box 1a)
        ord_val = kwargs.get("ordinary_dividends") if kwargs.get("ordinary_dividends") is not None else kwargs.get("ordinary_amount", "0.00")
        self.ordinary_dividends = Decimal(str(ord_val))
        
        # 合格股利金額 (對應 1099-DIV Box 1b，用於申報 1040 Line 3a 享有較低稅率)
        qual_val = kwargs.get("qualified_dividends") if kwargs.get("qualified_dividends") is not None else kwargs.get("qualified_amount", "0.00")
        self.qualified_dividends = Decimal(str(qual_val))
        
        # 免稅利息股利金額 (對應 1099-DIV Box 12，用於 1040 Line 2a 免稅利息合計)
        exempt_val = kwargs.get("exempt_interest_dividends") if kwargs.get("exempt_interest_dividends") is not None else kwargs.get("exempt_interest_amount", "0.00")
        self.exempt_interest_dividends = Decimal(str(exempt_val))
        


    def to_dict(self) -> Dict[str, Any]:
        """
        將物件序列化成 Python dict 格式，並將 Decimal 金額轉回 float 以利 JSON 傳輸。
        """
        return {
            "item_id": self.item_id,
            "source_statement_id": self.source_statement_id,
            "statement_issuer_name": self.statement_issuer_name,
            "source_document_type": self.source_document_type,
            "payer_name": self.payer_name,
            "ordinary_dividends": float(self.ordinary_dividends),
            "qualified_dividends": float(self.qualified_dividends),
            "exempt_interest_dividends": float(self.exempt_interest_dividends),
        }

class MarketDiscountItemV1:
    """
    [Layer 1] 市場折價項目模型 (Market Discount Item Model)
    
    用於申報已處分債券的應計市場折價 (Accrued Market Discount)，這部分在處分時認列為應稅利息。
    """
    def __init__(self, **kwargs):
        """
        初始化市場折價項目，包含成交金額 (proceeds) 與成本 (cost_basis)。
        """
        self.item_id = str(kwargs.get("item_id", ""))
        self.payer_name = kwargs.get("payer_name")
        self.proceeds = Decimal(str(kwargs.get("proceeds", "0.00")))
        self.cost_basis = Decimal(str(kwargs.get("cost_basis", "0.00")))
        self.accrued_market_discount = Decimal(str(kwargs.get("accrued_market_discount", "0.00")))

    def to_dict(self) -> Dict[str, Any]:
        """
        將市場折價資料序列化成 Python dict，將 Decimal 金額轉為 float。
        """
        return {
            "item_id": self.item_id,
            "payer_name": self.payer_name,
            "proceeds": float(self.proceeds),
            "cost_basis": float(self.cost_basis),
            "accrued_market_discount": float(self.accrued_market_discount),
        }

class Form8815V1:
    """
    [Layer 1] Form 8815 參考資料模型
    
    對應 Form 8815 教育儲蓄債券利息排除額。本引擎不計算 Form 8815 本身，而是引用其最終計算好的結果。
    """
    def __init__(self, **kwargs):
        """
        初始化 Form 8815 參照。
        """
        self.is_completed = bool(kwargs.get("is_completed", False))  # 代表 Form 8815 是否已確實填寫完畢
        self.line_14_excludable_interest = Decimal(str(kwargs.get("line_14_excludable_interest", "0.00")))  # 可排除利息金額
        self.eligible_series_ee_i_interest_included_in_line_2 = Decimal(str(kwargs.get("eligible_series_ee_i_interest_included_in_line_2", "0.00")))  # 包含在 Schedule B Line 2 裡的合格利息

    def to_dict(self) -> Dict[str, Any]:
        """
        將 Form 8815 參照資料序列化成 dict，將 Decimal 金額轉為 float。
        """
        return {
            "is_completed": self.is_completed,
            "line_14_excludable_interest": float(self.line_14_excludable_interest),
            "eligible_series_ee_i_interest_included_in_line_2": float(self.eligible_series_ee_i_interest_included_in_line_2),
        }

class SpecialCaseFlagsBV1:
    """
    [Layer 1] 特殊案件標籤模型 (Special Case Flags)
    
    定義 V1 引擎不支援的各類特殊申報情況。若任一旗標為 True，核心引擎將會拋出阻斷錯誤 (blocking error)。
    """
    def __init__(self, **kwargs):
        """
        初始化特殊案件旗標。
        """
        self.has_nominee_distribution = bool(kwargs.get("has_nominee_distribution", False))  # 代收代付申報
        self.has_accrued_interest = bool(kwargs.get("has_accrued_interest", False))          # 應計利息調整
        self.has_oid = bool(kwargs.get("has_oid", False))                                    # 原始折價發行 (Original Issue Discount)
        self.has_abp_adjustment = bool(kwargs.get("has_abp_adjustment", False))              # 可攤銷債券溢價 (Amortizable Bond Premium)
        self.has_market_discount = bool(kwargs.get("has_market_discount", False))            # 市場折價 (V1 只支援有明確 proceeds/cost 的計算)
        self.has_seller_financed_mortgage = bool(kwargs.get("has_seller_financed_mortgage", False)) # 賣方融資房貸
        self.has_form_8814 = bool(kwargs.get("has_form_8814", False))                        # 合併申報子女利息股利
        self.has_tax_exempt_bond_premium = bool(kwargs.get("has_tax_exempt_bond_premium", False))  # 免稅債券溢價
        self.has_contingent_payment_debt = bool(kwargs.get("has_contingent_payment_debt", False))  # 或有支付債務工具

    def to_dict(self) -> Dict[str, Any]:
        """
        將特殊案件旗標序列化成 dict 格式。
        """
        return {
            "has_nominee_distribution": self.has_nominee_distribution,
            "has_accrued_interest": self.has_accrued_interest,
            "has_oid": self.has_oid,
            "has_abp_adjustment": self.has_abp_adjustment,
            "has_market_discount": self.has_market_discount,
            "has_seller_financed_mortgage": self.has_seller_financed_mortgage,
            "has_form_8814": self.has_form_8814,
            "has_tax_exempt_bond_premium": self.has_tax_exempt_bond_premium,
            "has_contingent_payment_debt": self.has_contingent_payment_debt,
        }

class ScheduleBInputsV1:
    """
    [Layer 1] Schedule B 總體輸入模型
    
    將 LLM 從文件抽取的結果進行強型別映射與封裝。它是 Layer 2 計算引擎接收的唯一輸入參數型別。
    """
    def __init__(self, **kwargs):
        """
        初始化輸入模型，將 nested dict 與 項目陣列 映射為上述定義的 Layer 1 強型別物件。
        """
        self.taxpayer_name = str(kwargs.get("taxpayer_name", ""))
        self.taxpayer_ssn = str(kwargs.get("taxpayer_ssn", ""))
        ty = kwargs.get("tax_year")
        try:
            self.tax_year = int(float(ty)) if ty is not None else None
        except (ValueError, TypeError):
            self.tax_year = None
        
        # 映射利息明細項目列表 (若缺失 item_id 則以 index 自動生成，維持與 Schedule A 相同防禦邏輯)
        interest_items = []
        for idx, x in enumerate(kwargs.get("interest_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"interest_{idx}"
                interest_items.append(InterestItemV1(**x))
            else:
                interest_items.append(x)
        self.interest_items = interest_items
        
        # 映射股利明細項目列表 (若缺失 item_id 則以 index 自動生成)
        dividend_items = []
        for idx, x in enumerate(kwargs.get("dividend_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"dividend_{idx}"
                dividend_items.append(DividendItemV1(**x))
            else:
                dividend_items.append(x)
        self.dividend_items = dividend_items
        
        # 映射市場折價明細項目列表 (若缺失 item_id 則以 index 自動生成)
        market_discount_items = []
        for idx, x in enumerate(kwargs.get("market_discount_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"market_discount_{idx}"
                market_discount_items.append(MarketDiscountItemV1(**x))
            else:
                market_discount_items.append(x)
        self.market_discount_items = market_discount_items
        
        # 映射 Form 8815 參考模型
        f8815 = kwargs.get("form_8815")
        self.form_8815 = Form8815V1(**f8815) if isinstance(f8815, dict) else f8815 if f8815 else Form8815V1()
        

        
        # Part III 國外帳戶與信託篩選問卷 (Screening Questions)
        self.foreign_account_q1 = kwargs.get("foreign_account_q1")
        if self.foreign_account_q1 is None:
            self.foreign_account_q1 = kwargs.get("foreign_accounts_interest") # 向下相容歷史欄位名
            
        self.fbar_q2 = kwargs.get("fbar_q2")
        self.foreign_countries = kwargs.get("foreign_countries") or []
        
        self.foreign_trust_q8 = kwargs.get("foreign_trust_q8")
        if self.foreign_trust_q8 is None:
            self.foreign_trust_q8 = kwargs.get("foreign_trust_distribution") # 向下相容歷史欄位名
            
        # 映射不支援特殊案件的 flag 控制
        flags = kwargs.get("special_case_flags")
        self.special_case_flags = SpecialCaseFlagsBV1(**flags) if isinstance(flags, dict) else flags if flags else SpecialCaseFlagsBV1()

    # 可能要重構 把職責分離
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleBInputsV1":
        """
        [工廠方法] 將來自 LLM 解析的原始 Dict / JSON 直接加載轉換成 ScheduleBInputsV1 物件。
        這是 LLM parser 與 計算引擎間的主要橋樑。
        """
        return cls(**data)

class ScheduleBResultV1:
    """
    [Layer 3] Schedule B 最終申報結果模型 (Surface Output Model)
    
    封裝核心計算完成後的輸出資料。每個屬性在意義上皆高度對齊 IRS 實體 Schedule B 表單上的指定位置與申報檢驗旗標。
    """
    def __init__(self, **kwargs):
        """
        初始化輸出結果，包含合計金額與表面填表值。
        """
        self.taxpayer_name = kwargs.get("taxpayer_name", "")
        self.taxpayer_ssn_masked = kwargs.get("taxpayer_ssn_masked", "")  # 去敏感後的 masked SSN
        ty = kwargs.get("tax_year")
        try:
            self.tax_year = int(float(ty)) if ty is not None else None
        except (ValueError, TypeError):
            self.tax_year = None
        
        # 已處理且做完 Decimal 格式化的明細資料
        self.processed_interest_items = kwargs.get("processed_interest_items") or []
        self.processed_dividend_items = kwargs.get("processed_dividend_items") or []
        
        # --- Part I: Interest (利息部分) ---
        self.line_1_payer_entries = kwargs.get("line_1_payer_entries") or []  # Line 1: 列出應稅利息付款人與金額
        self.interest_subtotal = kwargs.get("interest_subtotal", Decimal("0.00")) # 利息小計 (Layer 2 中間計算值)
        self.line_2_total_interest = kwargs.get("line_2_total_interest", Decimal("0.00")) # Line 2: 應稅利息總額
        self.line_3_excludable_savings_bond_interest = kwargs.get("line_3_excludable_savings_bond_interest", Decimal("0.00")) # Line 3: 排除教育儲蓄債券利息
        self.line_4_raw_calculation = kwargs.get("line_4_raw_calculation", Decimal("0.00")) # Line 4 原始相減結果
        self.line_4_surface_value = kwargs.get("line_4_surface_value") # Line 4 實體表單表面填寫值 (小於零則留空，並拋出 validation 錯誤)
        
        # --- Part II: Ordinary Dividends (普通股利部分) ---
        self.line_5_payer_entries = kwargs.get("line_5_payer_entries") or []  # Line 5: 列出普通股利付款人與金額
        self.dividend_subtotal = kwargs.get("dividend_subtotal", Decimal("0.00")) # 股利小計
        self.line_6_total_ordinary_dividends = kwargs.get("line_6_total_ordinary_dividends", Decimal("0.00")) # Line 6: 普通股利總額
        
        # --- 跨表連動中間金額 ---
        self.total_tax_exempt_interest = kwargs.get("total_tax_exempt_interest", Decimal("0.00"))  # 免稅利息
        self.total_qualified_dividends = kwargs.get("total_qualified_dividends", Decimal("0.00"))   # 合格股利 (用於 1040 Line 3a)
        self.total_exempt_interest_dividends = kwargs.get("total_exempt_interest_dividends", Decimal("0.00")) # 免稅利息股利
        self.form_1040_line_2a = kwargs.get("form_1040_line_2a", Decimal("0.00"))                   # 應填入 1040 Line 2a 之總額
        
        # --- 申報判定旗標 ---
        self.is_part_iii_required = bool(kwargs.get("is_part_iii_required", False))    # 是否必須填寫 Part III 國外帳戶問卷
        self.is_schedule_b_required = bool(kwargs.get("is_schedule_b_required", False)) # 是否必須檢附 Schedule B 表單
        
        # --- Part III: Foreign Accounts and Trusts (國外帳戶與信託問卷之表面填寫值) ---
        # 說明：依據 IRS 申報指南，若 is_part_iii_required 為 False，即使有填寫問卷，表面欄位亦須渲染為 null (留白)。
        self.line_7a_q1_surface = kwargs.get("line_7a_q1_surface")  # Line 7a 第一問表面值 (是否有海外帳戶)
        self.line_7a_q2_surface = kwargs.get("line_7a_q2_surface")  # Line 7a 第二問表面值 (是否需申報 FBAR)
        self.line_7b_surface = kwargs.get("line_7b_surface")        # Line 7b 表面值 (海外帳戶所在國家名稱串接，e.g., 'Taiwan, Japan')
        self.line_8_surface = kwargs.get("line_8_surface")          # Line 8 表面值 (是否有國外信託分配)
        
        # --- 引擎執行狀態與錯誤元數據 ---
        self.blocking_errors = kwargs.get("blocking_errors") or []       # 阻斷型驗證錯誤列表 (若存在，則不能進行自動申報)
        self.review_warnings = kwargs.get("review_warnings") or []       # 審查提示警告列表
        self.blocking_validation_error = bool(kwargs.get("blocking_validation_error", False)) # 是否有任何阻斷錯誤
        self.is_v1_supported = bool(kwargs.get("is_v1_supported", True)) # 本次申報資料是否在 V1 引擎支援範圍內
        self.can_file = bool(kwargs.get("can_file", True))               # 能否進行電子申報
        self.should_attach_schedule_b = bool(kwargs.get("should_attach_schedule_b", False)) # 是否需要附上 Schedule B 申報

    def to_dict(self) -> Dict[str, Any]:
        """
        將核心計算引擎輸出結果物件轉換為標準的 Python dict。
        主要是為了解決 Decimal 無法直接進行 JSON 序列化的問題（全部轉換成 float 或 string 原始型別）。
        """
        def to_float(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
            
        def convert_item(item):
            if hasattr(item, "to_dict"):
                return item.to_dict()
            return item

        return {
            "taxpayer_name": self.taxpayer_name,
            "taxpayer_ssn_masked": self.taxpayer_ssn_masked,
            "tax_year": self.tax_year,
            "processed_interest_items": [convert_item(x) for x in self.processed_interest_items],
            "processed_dividend_items": [convert_item(x) for x in self.processed_dividend_items],
            "line_1_payer_entries": [
                {k: to_float(v) for k, v in entry.items()} if isinstance(entry, dict) else entry
                for entry in self.line_1_payer_entries
            ],
            "interest_subtotal": to_float(self.interest_subtotal),
            "line_2_total_interest": to_float(self.line_2_total_interest),
            "line_3_excludable_savings_bond_interest": to_float(self.line_3_excludable_savings_bond_interest),
            "line_4_raw_calculation": to_float(self.line_4_raw_calculation),
            "line_4_surface_value": to_float(self.line_4_surface_value),
            "line_5_payer_entries": [
                {k: to_float(v) for k, v in entry.items()} if isinstance(entry, dict) else entry
                for entry in self.line_5_payer_entries
            ],
            "dividend_subtotal": to_float(self.dividend_subtotal),
            "line_6_total_ordinary_dividends": to_float(self.line_6_total_ordinary_dividends),
            "total_tax_exempt_interest": to_float(self.total_tax_exempt_interest),
            "total_qualified_dividends": to_float(self.total_qualified_dividends),
            "total_exempt_interest_dividends": to_float(self.total_exempt_interest_dividends),
            "form_1040_line_2a": to_float(self.form_1040_line_2a),
            "is_part_iii_required": self.is_part_iii_required,
            "is_schedule_b_required": self.is_schedule_b_required,
            "line_7a_q1_surface": self.line_7a_q1_surface,
            "line_7a_q2_surface": self.line_7a_q2_surface,
            "line_7b_surface": self.line_7b_surface,
            "line_8_surface": self.line_8_surface,
            "blocking_errors": [err.to_dict() if hasattr(err, "to_dict") else err for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() if hasattr(warn, "to_dict") else warn for warn in self.review_warnings],
            "blocking_validation_error": self.blocking_validation_error,
            "is_v1_supported": self.is_v1_supported,
            "can_file": self.can_file,
            "should_attach_schedule_b": self.should_attach_schedule_b,
        }
