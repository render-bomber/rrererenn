


async def hold_connection(sem, stats):
    while True:
        async with sem:
            if time.time() - stats["start"] > DURATION:
                return
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(TARGET_HOST, TARGET_PORT),
                    timeout=2.0
                )
                async with stats["lock"]:
                    stats["ok"] += 1
                    stats["total"] += 1

                # Держим соединение открытым 5 секунд (имитация зависшего клиента)
                await asyncio.sleep(5)

                try:
                    writer.close()
                    await writer.wait_closed()
                except:
                    pass
            except asyncio.TimeoutError:
                async with stats["lock"]:
                    stats["timeout"] += 1
                    stats["total"] += 1
            except Exception:
                async with stats["lock"]:
                    stats["fail"] += 1
                    stats["total"] += 1


async def main():
    print(f"[*] Target: {TARGET_HOST}:{TARGET_PORT}")
    print(f"[*] Concurrency: {CONCURRENCY} | Duration: {DURATION}s")
    print("-" * 50)

    stats = {"start": time.time(), "ok": 0, "fail": 0, "timeout": 0, "total": 0, "lock": asyncio.Lock()}
    sem = asyncio.Semaphore(CONCURRENCY)

    workers = [asyncio.create_task(hold_connection(sem, stats)) for _ in range(CONCURRENCY)]

    while time.time() - stats["start"] < DURATION:
        await asyncio.sleep(2)
        elapsed = time.time() - stats["start"]
        rps = stats["total"] / elapsed if elapsed > 0 else 0
        print(
            f"[*] {elapsed:.0f}s | OK: {stats['ok']} | FAIL: {stats['fail']} | TIMEOUT: {stats['timeout']} | RPS: {rps:.0f}")

    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    elapsed = time.time() - stats["start"]
    print("-" * 50)
    print(f"[+] Done in {elapsed:.0f}s")
    print(f"[+] Total: {stats['total']} | OK: {stats['ok']} | FAIL: {stats['fail']} | TIMEOUT: {stats['timeout']}")
    print(f"[+] Avg RPS: {stats['total'] / elapsed:.0f}")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Stopped by user.")