# Clean up

Workshop accounts are deleted automatically 72 hours after the event, so you only need this to reset mid-day or to clean up your own account.

!!! warning "Capstone: download your export first"
    `exports/<squad>-agent-skeleton.zip` is lost with the account. Download it from the Code Editor file tree before cleaning up.

Run these in order. Factory agents are not in the CloudFormation stack, so delete them first.

| Step | Command | Removes |
|---|---|---|
| 1 | `make destroy-agent NAME=<product>` | One factory agent (Lab B `payments-gw`, and each capstone service): Gateway, policy engine and policies, memory, Runtime, custom Lambdas |
| 2 | `make reset-labA` | Lab A's Gateway, policy engine, memory and Runtime. **Keeps** the bootstrap stack, so you can start Lab A again from Part 1 |
| 3 | `make destroy` | Everything else, including the `DezervLabA` stack and both S3 buckets |

```bash
make destroy-agent NAME=payments-gw
make reset-labA
make destroy
```

`make destroy` needs working credentials for the account recorded in `.env`. Set `EXPECT_ACCOUNT` so it can't touch any other account.
