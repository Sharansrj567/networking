# NS-3 TCP Experiment Simulation

This project contains a single NS-3 simulation that measures and compares throughput and flow-completion times of various TCP variants (TCP-BIC, DCTCP, and mixed) over a dumbbell topology.

## Requirements

- NS-3 (tested with `ns-3.35` or later)  
- A C++11-capable compiler toolchain  
- Python 3 (for optional post-processing)

## Building

1. Copy `dumbbell-topology.cpp` into your NS-3 `scratch/` directory.  
2. Reconfigure and rebuild NS-3:
  ```sh
  cd ~/ns-3
  ./waf configure --enable-examples --enable-tests
  ./waf build
  ```

## Running

Run the simulation with:
```sh
./waf --run scratch/dumbbell-topology.cpp
```

## Output

After completion, you will find:

- `tcp_srjamana.csv` – throughput and flow-completion time statistics for each experiment  
  Columns include per-run measurements (`r1_*`, `r2_*`, `r3_*`), averages, standard deviations, and units.

## Experiment Overview

1. Single flow using **TCP-BIC**  
2. Two concurrent flows using **TCP-BIC**  
3. Single flow using **DCTCP**  
4. Two concurrent flows using **DCTCP**  
5. One **TCP-BIC** flow vs. one **DCTCP** flow (mixed)  

Each flow runs for 3 × 10 s segments; statistics are aggregated across runs.
