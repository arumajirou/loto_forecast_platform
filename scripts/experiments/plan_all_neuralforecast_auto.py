import sys

from loto.auto_campaign.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "plan")
    main()
