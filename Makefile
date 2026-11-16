# Dezerv labs. All data is synthetic. Account is taken from your credentials; set EXPECT_ACCOUNT to guard against the wrong one.
PY    = uv run --python 3.12 --with boto3
AGENT = uv run --python 3.12 --with boto3 --with strands-agents --with mcp --with bedrock-agentcore --with opentelemetry-api
EVAL  = uv run --python 3.12 --with boto3 --with deepeval
FACT  = uv run --python 3.12 --with boto3 --with pyyaml --with jinja2 --with jsonschema
TEST  = uv run --python 3.12 --with pytest --with boto3 --with pyyaml --with jinja2 --with jsonschema
GUARD = $(if $(EXPECT_ACCOUNT),--expect-account $(EXPECT_ACCOUNT),)

# `make go-setup` may install Go to ~/.local/go (no brew/root). Put it on PATH for every recipe and child process
# (factory/deploy.py, verify_b.py, preflight.py), so no shell restart or profile edit is needed to use make targets.
export PATH := $(HOME)/.local/go/bin:$(PATH)

.PHONY: help grant-passrole preflight bootstrap gateway policy interceptors freeze-on freeze-off memory seed-memory run-incident run-injection \
        deploy-agent eval gate break-prompt fix-prompt test token destroy reset-labA \
        solution-part1 solution-part2 solution-part3 solution-part4 solution-part5 solution-part6 solution-all cp6 cp6-off \
        new-agent destroy-agent link-labA go-setup go-test go-prebuild go-prebuilt run-forwarder test-factory \
        solution-labB-part1 solution-labB-part2 solution-labB-part3 solution-labB-part4 \
        verify-bootstrap verify-labA-part1 verify-labA-part2 verify-labA-part3 verify-labA-part4 verify-labA-part5 verify-labA-part6 \
        verify-labB-part1 verify-labB-part2 verify-labB-part3 verify-labB-part4 \
        new-squad provision-squad prove-denial verify-capstone export new-tool test-capstone

help:           ## list targets
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ -/'

# --- Lab A -----------------------------------------------------------------------------------------------------------
grant-passrole: ## ONCE per account, from the default CodeEditorInstanceRole terminal: let WSParticipantRole pass the Lab A roles
	bash scripts/grant_passrole.sh
preflight:      ## FIRST: can this machine and account run the labs? (read-only; checks tools, internet, IAM, Bedrock model)
	$(PY) python scripts/preflight.py
bootstrap:      ## build + deploy stack DezervLabA, seed data, write .env
	$(PY) python scripts/bootstrap.py $(GUARD)
gateway:        ## Part 1: Gateway + 6 Lambda targets
	$(PY) python scripts/labA.py gateway
policy:         ## Part 2: policy engine + Cedar pack (ENFORCE)
	$(PY) python scripts/labA.py policy
interceptors:   ## Part 3: attach interceptor (rate limit, freeze, PII mask, untrusted tags)
	$(PY) python scripts/labA.py interceptors
freeze-on:      ## Part 3: change freeze on
	$(PY) python scripts/labA.py freeze on
freeze-off:     ## Part 3: change freeze off
	$(PY) python scripts/labA.py freeze off
memory:         ## Part 5: create the memory resource
	$(PY) python scripts/labA.py memory
seed-memory:    ## Part 5: load 26 incidents + 8 runbooks
	$(PY) python scripts/seed_memory.py
run-incident:   ## run the agent on the lab incident (PERSONA=oncall|support)
	$(AGENT) python agent/main.py --persona $(or $(PERSONA),oncall) --task incident
run-injection:  ## run the agent on the ticket containing the injection
	$(AGENT) python agent/main.py --persona $(or $(PERSONA),oncall) --task injection
deploy-agent:   ## Lab A Part 6: deploy the agent to Runtime. With NAME=<product>: deploy the factory-rendered agent (Lab B)
	$(if $(NAME),$(FACT) python factory/deploy.py $(NAME),$(PY) python scripts/deploy_runtime.py)
eval:           ## Part 6: replay 10 incidents against the deployed agent (NAME=<product> for a factory agent)
	$(if $(NAME),RUNTIME_ARN=$$(python3 -c "import json;print(json.load(open('agents/$(NAME)/.state.json'))['runtime_arn'])") $(EVAL) python evals/run_eval.py --out agents/$(NAME)/report.json --replay $$(python3 -c "import json;print(json.load(open('agents/$(NAME)/evals/gates.json'))['replay'])"),$(EVAL) python evals/run_eval.py --out $(or $(OUT),evals/report.json))
gate:           ## Part 6: CI gate (exit 1 on failure). REPORT=report_baseline.json to pick another report; NAME= for a factory agent
	$(if $(NAME),python3 evals/gate.py agents/$(NAME)/report.json agents/$(NAME)/evals/gates.json,python3 evals/gate.py $(or $(REPORT),report.json))
break-prompt:   ## Part 6: remove the untrusted + cite rules (then deploy-agent, eval, gate)
	python3 scripts/break_prompt.py break
fix-prompt:     ## restore the prompt rules
	python3 scripts/break_prompt.py fix
cp6:            ## apply the CP-6 solution (ledger-svc forbidden zone)
	cp policy/solutions/60-forbid-ledger-zone.cedar policy/cedar/ && $(MAKE) policy
cp6-off:        ## remove the CP-6 rule again
	rm -f policy/cedar/60-forbid-ledger-zone.cedar && $(PY) python scripts/labA.py policy

# --- fast-forward: bring an account to the END of part N (idempotent; safe to re-run) --------------------------------
solution-part1: bootstrap gateway                                  ## catch up: end of Part 1
solution-part2: solution-part1 policy                              ## catch up: end of Part 2
solution-part3: solution-part2 interceptors                        ## catch up: end of Part 3
solution-part4: solution-part3                                     ## catch up: end of Part 4 (audit hooks are always on in agent/)
	@echo "Audit hooks need no setup; run make run-incident then make verify-labA-part4"
solution-part5: solution-part4 memory seed-memory                  ## catch up: end of Part 5
solution-part6: solution-part5 deploy-agent                        ## catch up: end of Part 6 setup (add: make eval / make gate)
solution-all: solution-part6                                       ## everything except the long eval run

# --- housekeeping ------------------------------------------------------------------------------------------------------
test:           ## unit tests (PII masking, anchor selection, factory)
	$(TEST) python -m pytest tests -q
test-factory:   ## factory tests only
	$(TEST) python -m pytest tests/test_factory.py -q
token:          ## print a Gateway token: make token PERSONA=support
	$(PY) python scripts/mcp_cli.py token --persona $(or $(PERSONA),oncall)
reset-labA:     ## delete Gateway, policy engine, memory, runtime (keeps bootstrap stack)
	$(PY) python scripts/labA.py reset
destroy:        ## delete everything including the stack (artifact bucket too)
	$(PY) python scripts/destroy.py

# --- Lab B: agent factory + Go -----------------------------------------------------------------------------------------
link-labA:      ## second editor: rebuild .env/.labA.json from the existing Lab A stack (no redeploy)
	$(PY) python scripts/link_labA.py
new-agent:      ## render an agent from a manifest: make new-agent NAME=payments-gw FROM=labs/B/agent.yaml
	$(FACT) python factory/render.py new-agent --from $(or $(FROM),labs/B/agent.yaml) $(if $(NAME),--name $(NAME),)
destroy-agent:  ## delete a factory agent's cloud resources: make destroy-agent NAME=payments-gw
	$(FACT) python factory/deploy.py $(NAME) --destroy
go-setup:       ## make sure a Go toolchain exists (already installed / brew / checked tarball)
	bash scripts/go_setup.sh
go-test:        ## go vet + go test for the Go tool and the Go forwarder
	cd tools/mandates-go && go vet ./... && go test ./...
	cd go/alert-forwarder && go vet ./... && go test ./...
go-prebuild:    ## (maintainers) build the prebuilt binaries committed under prebuilt/
	bash scripts/go_prebuild.sh
go-prebuilt:    ## attendees without Go: install the prebuilt forwarder to bin/alert-forwarder
	bash scripts/go_prebuild.sh --install
# forwarder port; 8080 is taken by the workshop editor (override: make run-forwarder PORT=9000)
PORT ?= 8090
run-forwarder:  ## run the Go alert forwarder in this terminal (NAME= for a factory agent, PORT= to change 8090); send the alert from a second terminal
	bash scripts/run_forwarder.sh "$(NAME)" "$(PORT)"

solution-labB-part1: link-labA           ## catch up: end of Lab B Part 1 (factory agent rendered + deployed). Needs Lab A: make solution-part6
	$(MAKE) new-agent NAME=payments-gw FROM=labs/B/agent.yaml
	$(MAKE) deploy-agent NAME=payments-gw
solution-labB-part2: solution-labB-part1 ## catch up: end of Part 2 (the Go forwarder needs no deployment)
	$(MAKE) go-test
solution-labB-part3: solution-labB-part2 ## catch up: end of Part 3 (Go tool added to the manifest and deployed)
	cp labs/B/solutions/agent.part3.yaml labs/B/agent.yaml
	$(MAKE) new-agent NAME=payments-gw FROM=labs/B/agent.yaml
	$(MAKE) deploy-agent NAME=payments-gw
solution-labB-part4: solution-labB-part3 ## catch up: end of Part 4 (forbidden zone added)
	cp labs/B/solutions/agent.part4.yaml labs/B/agent.yaml
	$(MAKE) new-agent NAME=payments-gw FROM=labs/B/agent.yaml
	$(MAKE) deploy-agent NAME=payments-gw

verify-bootstrap verify-labA-part1 verify-labA-part2 verify-labA-part3 verify-labA-part4 verify-labA-part5 verify-labA-part6:
	$(PY) python scripts/verify.py $@
verify-labB-part1 verify-labB-part2 verify-labB-part3 verify-labB-part4:
	$(FACT) python scripts/verify_b.py $@

# --- Capstone ------------------------------------------------------------------------------------------------------------
new-squad:      ## generate a squad: make new-squad SQUAD=kyc PROFILE=kyc-svc   (or SCHEMA=my-service.yaml)
	$(FACT) python tools/gen_profile.py $(if $(SCHEMA),--schema $(SCHEMA),--profile $(PROFILE)) --squad $(SQUAD)
provision-squad: ## upload the squad's synthetic data, backfill its logs, add its injection ticket: make provision-squad SQUAD=kyc
	$(FACT) python scripts/squad.py provision $(SQUAD)
prove-denial:   ## show a forbidden-zone call denied in the audit log: make prove-denial SQUAD=kyc
	$(AGENT) --with pyyaml --with jinja2 --with jsonschema python scripts/squad.py prove-denial $(SQUAD)
verify-capstone: ## checkpoints: make verify-capstone SQUAD=kyc CHECK=C1|C2|C3
	$(AGENT) --with pyyaml --with jinja2 --with jsonschema python scripts/squad.py verify $(SQUAD) $(or $(CHECK),C1)
export:         ## zip the squad's skeleton: make export SQUAD=kyc  -> exports/kyc-agent-skeleton.zip
	$(FACT) python scripts/squad.py export $(SQUAD)
new-tool:       ## scaffold a custom tool: make new-tool SQUAD=kyc TOOL=get_x ARG=request_id [RUNTIME=python|go]
	$(FACT) python scripts/squad.py new-tool $(SQUAD) $(TOOL) $(ARG) --runtime $(or $(RUNTIME),python)
test-capstone:  ## every ready profile generates a valid, renderable squad
	$(TEST) python -m pytest tests/test_capstone.py -q
