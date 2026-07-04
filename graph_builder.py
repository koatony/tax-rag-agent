"""
知識圖譜推理子圖建構器
==============================
從檢索到的核心法規 (Rule) 出發，沿著圖譜關係擴展出完整的 IRAC 結構。
"""

from data_models import NodeInfo, RuleCandidate, IRACSubgraph
from kg_manager import KGIndex, VectorIndex

class SubgraphBuilder:
    """
    負責在圖譜中進行遍歷，將法規、事實與結論組裝成推理鏈。
    """
    def __init__(self, kg: KGIndex, rule_index: VectorIndex = None, fact_index: VectorIndex = None):
        self.kg = kg
        self.rule_index = rule_index
        self.fact_index = fact_index

    def _resolve_id(self, entity_id: str, id_type: str = "rule") -> str:
        """將雜湊 ID 轉換為實體名稱 (用於 Neo4j 橋接)"""
        if id_type == "rule" and self.rule_index:
            return self.rule_index.get_name(entity_id)
        if id_type == "fact" and self.fact_index:
            return self.fact_index.get_name(entity_id)
        return entity_id

    def build(self, rule_candidate: RuleCandidate) -> IRACSubgraph:
        """從核心法規點開始擴展"""
        # 🔑 解析 ID (如果是雜湊則換成名稱)
        rule_id = self._resolve_id(rule_candidate.rule_id, "rule")
        rule_info = rule_candidate.rule_info
        
        sg = IRACSubgraph(rule=rule_info, final_score=rule_candidate.final_score, is_dual_hit=rule_candidate.is_dual_hit)

        # 找涉及議題 (Issues)
        for nb, rel in self.kg.get_neighbors(rule_id, relation="ADDRESSES", direction="both"):
            if nb.entity_type == "legalissue": sg.issues.append(nb)

        # 找事實要件 (Facts)
        for nb, rel in self.kg.get_neighbors(rule_id, relation="APPLIED_TO", direction="out"):
            if nb.entity_type == "materialfact": sg.facts.append(nb)

        # 補入 Track B 命中的事實點
        for fid in rule_candidate.matched_fact_ids:
            # 🔑 解析事實 ID
            resolved_fid = self._resolve_id(fid, "fact")
            node = self.kg.get_node(resolved_fid)
            if node and node not in sg.facts:
                sg.facts.append(node)

        # 若無事實，嘗試從法規描述文字中解析 (Fallback)
        if not sg.facts and "Conditions:" in rule_info.description:
            cond_text = self._extract_conditions(rule_info.description)
            if cond_text:
                sg.facts.append(NodeInfo(entity_id=f"[FALLBACK] {rule_id}", entity_type="materialfact", 
                                       description=cond_text, source_id=rule_info.source_id, file_path=rule_info.file_path))

        # 遞迴找結論 (Conclusions)
        self._find_conclusions(rule_id, sg, depth=0, max_depth=2)

        # 找引用來源 (Regulations)
        for nb, rel in self.kg.get_neighbors(rule_id, relation="DERIVES_FROM", direction="out"):
            if nb.entity_type in ("regulation", "statute"): sg.regulations.append(nb)

        return sg

    def _find_conclusions(self, node_id: str, sg: IRACSubgraph, depth: int, max_depth: int):
        """遞迴查找後續結論節點"""
        if depth >= max_depth: return
        for nb, rel in self.kg.get_neighbors(node_id, direction="out"):
            if rel in ("LEADS_TO", "YIELDS_TO") and nb.entity_type == "conclusion":
                if nb not in sg.conclusions: sg.conclusions.append(nb)
                # 這裡的 nb.entity_id 已經是名稱了 (如果是 Neo4j 傳回來的)
                self._find_conclusions(nb.entity_id, sg, depth + 1, max_depth)

    def _extract_conditions(self, description: str) -> str:
        """從描述中提取 'Conditions:' 關鍵字之後的內容"""
        for segment in description.split("|"):
            if segment.strip().lower().startswith("conditions:"): return segment.strip()
        return ""
