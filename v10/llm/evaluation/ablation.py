ABLATION_CONFIGS = {
    "A_no_llm": {"luna": False, "terra": False, "sol": False},
    "B_luna_only": {"luna": True, "terra": False, "sol": False},
    "C_terra_panels": {"luna": True, "terra": True, "sol": False},
    "D_full_cascade": {"luna": True, "terra": True, "sol": True},
    "E_all_agents_separate": {"benchmark_only": True, "default": False},
}
