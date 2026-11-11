import os
import sys


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "niochat_sa.settings")
    try:
        import django

        django.setup()
    except Exception as exc:
        print(f"[billing-auto-block] django.setup failed: {exc}", file=sys.stderr)
        return 2

    from super_core.billing_auto_block import run_billing_auto_block_cycle

    result = run_billing_auto_block_cycle()
    if result.get("blocked"):
        print(
            f"[billing-auto-block] blocked={result.get('blocked')} "
            f"checked={result.get('checked')} min_days={result.get('min_days')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

