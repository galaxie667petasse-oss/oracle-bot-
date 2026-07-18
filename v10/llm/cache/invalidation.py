def invalidation_reasons(old_packet_hash: str, new_packet_hash: str) -> list[str]:
    if old_packet_hash != new_packet_hash:
        return ["candidate_packet_changed"]
    return []
