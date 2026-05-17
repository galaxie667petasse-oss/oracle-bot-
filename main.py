# Stable Railway entrypoint.
# Keep Railway Start Command fixed to: python main.py
# To upgrade versions later, only change CURRENT_MODULE below.

CURRENT_MODULE = "oracle_bot_v45"

module = __import__(CURRENT_MODULE)
module.main()
