import json
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional


class TaxRuleNotFoundError(Exception):
    """稅率或 Tax Table 查表找不到匹配項時拋出的例外"""
    pass


class TaxRuleProvider:
    """
    2025 IRS 稅率與 Tax Table / Worksheet 單例服務提供者 (Singleton/Cached Provider)
    
    職責：
    1. 從 json 檔案載入 2025 Tax Table (查表法) 與 Tax Computation Worksheet (公式法)。
    2. 提供 `lookup_tax_table` 供 Line 15 < $100,000 的案件查詢。
    3. 提供 `compute_tax_computation_worksheet` 供 Line 15 >= $100,000 的案件套算。
    """
    _instance: Optional["TaxRuleProvider"] = None

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        rules_2025_path = os.path.join(base_dir, "2025", "tax_rules_2025.json")
        table_2025_path = os.path.join(base_dir, "2025", "tax_table_2025.json")

        with open(rules_2025_path, "r", encoding="utf-8") as f:
            self.rules_2025: Dict[str, Any] = json.load(f)

        with open(table_2025_path, "r", encoding="utf-8") as f:
            table_data = json.load(f)
            if isinstance(table_data, dict) and "rows" in table_data:
                self.table_2025: List[Dict[str, Any]] = table_data["rows"]
            else:
                self.table_2025 = table_data


    @classmethod
    def get_instance(cls) -> "TaxRuleProvider":
        """取得 TaxRuleProvider 的單例實例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _resolve_status_key(self, filing_status: str) -> str:
        """處理 Filing Status 別名（例如 QSS 映射至 MFJ）"""
        status_upper = filing_status.upper()
        aliases = self.rules_2025.get("filing_status_aliases", {})
        mapped = aliases.get(status_upper, status_upper)
        return mapped.lower()

    def lookup_tax_table(self, filing_status: str, taxable_income: Decimal) -> Decimal:
        """
        查 2025 IRS Tax Table (Line 15 < $100,000)
        
        :param filing_status: 報稅身份 (SINGLE, MFJ, MFS, HOH, QSS)
        :param taxable_income: 應稅所得 Line 15
        :return: IRS Tax Table 查得之應納稅額 (whole dollar Decimal)
        """
        status_key = self._resolve_status_key(filing_status)
        inc_val = Decimal(str(taxable_income))

        for row in self.table_2025:
            income_from = Decimal(str(row["income_from"]))
            income_to = Decimal(str(row["income_to_exclusive"]))

            if income_from <= inc_val < income_to:
                if status_key not in row:
                    raise TaxRuleNotFoundError(f"Status key '{status_key}' not found in tax table row.")
                tax_amt = Decimal(str(row[status_key]))
                return tax_amt.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        raise TaxRuleNotFoundError(
            f"未能在 2025 IRS Tax Table 中找到對應所得區間: ${taxable_income} (Filing Status: {filing_status})"
        )

    def compute_tax_computation_worksheet(self, filing_status: str, taxable_income: Decimal) -> Decimal:
        """
        使用 2025 Tax Computation Worksheet 計算 (Line 15 >= $100,000)
        
        公式：tax = (taxable_income * rate) - subtract
        結果四捨五入至整數 (ROUND_HALF_UP)
        """
        status_upper = filing_status.upper()
        aliases = self.rules_2025.get("filing_status_aliases", {})
        status_key = aliases.get(status_upper, status_upper)

        worksheet_dict = self.rules_2025.get("tax_computation_worksheet", {})
        if status_key not in worksheet_dict:
            raise TaxRuleNotFoundError(f"No 2025 worksheet rules found for filing status '{status_key}'.")

        rows = worksheet_dict[status_key]
        inc_val = Decimal(str(taxable_income))

        for row in rows:
            lower_inc = Decimal(str(row["lower_inclusive"])) if "lower_inclusive" in row else None
            lower_exc = Decimal(str(row["lower_exclusive"])) if "lower_exclusive" in row else None
            upper_inc = Decimal(str(row["upper_inclusive"])) if row.get("upper_inclusive") is not None else None

            # 檢查區間匹配
            matches_lower = True
            if lower_inc is not None and inc_val < lower_inc:
                matches_lower = False
            if lower_exc is not None and inc_val <= lower_exc:
                matches_lower = False

            matches_upper = True
            if upper_inc is not None and inc_val > upper_inc:
                matches_upper = False

            if matches_lower and matches_upper:
                rate = Decimal(str(row["rate"]))
                subtract = Decimal(str(row["subtract"]))
                calculated_tax = (inc_val * rate) - subtract
                return calculated_tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        raise TaxRuleNotFoundError(
            f"未能在 2025 Tax Computation Worksheet 中找到對應區間: ${taxable_income} (Filing Status: {filing_status})"
        )
