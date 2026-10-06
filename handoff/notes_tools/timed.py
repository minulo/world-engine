import resource, subprocess, sys, time
t = time.time()
code = subprocess.call(sys.argv[2:], stdout=open(sys.argv[1], "w"), stderr=subprocess.STDOUT)
peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1e6
open(sys.argv[1] + ".time", "w").write(f"{time.time() - t:.1f} s; peak memory {peak:.2f} GB; exit {code}\n")
