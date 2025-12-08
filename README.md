# python-batchtools

## Overview

`python-batchtools` is a CLI for students and researchers to
submit **GPU batch jobs** through Kueue-managed GPU queues on an
OpenShift cluster. It provides an inexpensive and accessible way to use
GPU hardware without reserving dedicated GPU nodes.

Users submit GPU jobs with a single command:

``` sh
batchtools br "./cuda_program"
```

The CLI will automatically:
- Creates the batch job<br>
- Submits it to the appropriate Kueue-managed LocalQueue<br>
- Tracks job status<br>
- Streams logs on completion <br>


# For Users

## Installation

### Option 1: Use the provided container image (recommended)

### Option 2: Install from source

``` sh
git clone https://github.com/memalhot/python-batchtools.git
cd python-batchtools
pip install -e .
```


## Prerequisites

1.  A Kueue-enabled OpenShift cluster, with localqueues named: v100-localqueue, a100-localqueue, h100-localqueue, dummy-localqueue<br>
2.  An OpenShift account<br>
3.  The Python OpenShift client:

``` sh
pip install openshift-client
```
4. RBAC permissions for the user to have access to jobs, kueue resources like localqueues and clusterqueues. See **rbac** folder for setup.

# Usage Examples

For any command you can run:
`batchtools <command> -h` or `batchtools <command> --help`

## **1. Submit a Batch Job --- `br`**
The br command is how to submit batchjobs. It submits code intended to run on GPUs to the Kueue, where it is queued, then run, produces logs stored in the `RUNDIR`, and then deletes the job for resource conservation.

Here's how to use thed br command:

First write a CUDA program and compile it :D <br>
Then to submit your CUDA program to the GPU node:

``` sh
batchtools br "./cuda-code"
```

Submit a program with arguments:

``` sh
batchtools br './simulate --steps 1000'
```

Specify GPU type:

``` sh
batchtools br --gpu v100 "./train_model"
```

Run without waiting for logs (for longer runs, similar to a more traditional batch system):

``` sh
batchtools br --no-wait "./cuda_program"
```
***WARNING***<br>
If you run br with the --no-wait flag, it will not be cleaned up for you. You must delete it on your own by running `batchtools bd <job-name>` or `oc delete job <job-name>`
But don't worry, running with --no-wait will give you a reminder to delete your jobs!<br>

And if you need help or want to see more flas:

``` sh
batchtools br --h
```


## **2. List Jobs --- `bj`**

List all jobs:

``` sh
batchtools bj
```


## **3. Delete Jobs --- `bd`**

Delete all jobs:

``` sh
batchtools bd
```

To delete specific jobs:

``` sh
batchtools bd job-a job-b
```


## **4. List active GPU pods per node --- `bps`**

``` sh
batchtools bps
```

Output will be empty if all nodes are free.

If some nodes are busy:
```
wrk-4: BUSY 3 project-1/project-stuff testing/other-stuff test/fraud-detectiob
```

To always ensure output, you can run:

``` sh
batchtools --verbose bps
```
To get output like:
```
ctl-0: FREE
ctl-1: FREE
ctl-2: FREE
wrk-0: FREE
wrk-1: FREE
wrk-3: FREE
wrk-4: BUSY 3 project-1/project-stuff testing/other-stuff test/fraud-detection
wrk-5: FREE
wrk-6: FREE
wrk-7: FREE

```

## **5. Show pod logs --- `bl`**

``` sh
batchtools bl
```

For a specific pod:
``` sh
batchtools bl pod-name
```


## **6. Show pod logs --- `bq`**

``` sh
batchtools bq
```

Output will look like:
``` sh
a100-clusterqueue       admitted: 0     pending: 0      reserved: 0     GPUs: 0 BestEffortFIFO
dummy-clusterqueue      admitted: 0     pending: 0      reserved: 0     GPUs: 0 BestEffortFIFO
h100-clusterqueue       admitted: 0     pending: 0      reserved: 0     GPUs: 0 BestEffortFIFO
v100-clusterqueue       admitted: 0     pending: 0      reserved: 0     GPUs: 3 BestEffortFIFO
```

# For Contributors

## Tools

Install uv:

``` sh
pipx install uv
```

Install pre-commit:

``` sh
pipx install pre-commit
```

Activate hooks:

``` sh
pre-commit install
```

## Running Tests

``` sh
uv run pytest
```

Coverage report is generated at:

    htmlcov/index.html
