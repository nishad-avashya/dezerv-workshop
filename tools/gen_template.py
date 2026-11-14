#!/usr/bin/env python3
"""Generates infra/template.yaml so the seven near-identical Lambda blocks stay consistent."""
fns = {
 "logs":      dict(mem=256, t=90, env={}),
 "db":        dict(mem=1024, t=60, env={"DATA_BUCKET": "!Ref DataBucket", "DATA_VERSION": "!Ref DataHash"}),
 "warehouse": dict(mem=1024, t=60, env={"DATA_BUCKET": "!Ref DataBucket", "DATA_VERSION": "!Ref DataHash"}),
 "changes":   dict(mem=256, t=30, env={"DATA_BUCKET": "!Ref DataBucket", "DATA_VERSION": "!Ref DataHash"}),
 "tickets":   dict(mem=256, t=30, env={"TICKETS_TABLE": "!Ref TicketsTable"}),
 "ops":       dict(mem=128, t=10, env={}),
 "interceptor": dict(mem=256, t=15, env={"RATE_TABLE": "!Ref RateTable", "FREEZE_PARAM": "/dezerv/freeze", "AUDIT_GROUP": "/dezerv/gateway-audit", "LIMIT_PER_MIN": "30"}),
}
head = r'''AWSTemplateFormatVersion: "2010-09-09"
Description: Dezerv Lab A bootstrap (synthetic data only). Gateway, Policy and Memory are created by scripts/labA.py.
Parameters:
  ArtifactBucket: {Type: String}
  CodeHash: {Type: String}
  DataHash: {Type: String, Default: none, Description: "changes whenever the seeded data changes, so Lambdas drop their per-container data cache"}
Resources:
  DataBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Delete
    Properties:
      BucketName: !Sub dezerv-laba-data-${AWS::AccountId}-${AWS::Region}
      PublicAccessBlockConfiguration: {BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true}
      BucketEncryption: {ServerSideEncryptionConfiguration: [{ServerSideEncryptionByDefault: {SSEAlgorithm: AES256}}]}
  PaymentsGwLogs: {Type: AWS::Logs::LogGroup, Properties: {LogGroupName: /dezerv/payments-gw, RetentionInDays: 14}}
  KycSvcLogs:     {Type: AWS::Logs::LogGroup, Properties: {LogGroupName: /dezerv/kyc-svc, RetentionInDays: 14}}
  AgentAuditLogs: {Type: AWS::Logs::LogGroup, Properties: {LogGroupName: /dezerv/agent-audit, RetentionInDays: 14}}
  GatewayAuditLogs: {Type: AWS::Logs::LogGroup, Properties: {LogGroupName: /dezerv/gateway-audit, RetentionInDays: 14}}
  TicketsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: dezerv-tickets
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions: [{AttributeName: key, AttributeType: S}]
      KeySchema: [{AttributeName: key, KeyType: HASH}]
  RateTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: dezerv-ratelimit
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions: [{AttributeName: pk, AttributeType: S}]
      KeySchema: [{AttributeName: pk, KeyType: HASH}]
  FreezeParam:
    Type: AWS::SSM::Parameter
    Properties: {Name: /dezerv/freeze, Type: String, Value: "off", Description: "Change freeze: on | off | <iso-start>/<iso-end>"}
  ToolRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument: {Version: "2012-10-17", Statement: [{Effect: Allow, Principal: {Service: lambda.amazonaws.com}, Action: sts:AssumeRole}]}
      ManagedPolicyArns: [arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole]
      Policies:
        - PolicyName: tools
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - {Effect: Allow, Action: s3:GetObject, Resource: !Sub "${DataBucket.Arn}/*"}
              - {Effect: Allow, Action: [logs:FilterLogEvents], Resource: !Sub "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/dezerv/*:*"}
              - {Effect: Allow, Action: [dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem, dynamodb:Scan, dynamodb:Query], Resource: !GetAtt TicketsTable.Arn}
  InterceptorRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument: {Version: "2012-10-17", Statement: [{Effect: Allow, Principal: {Service: lambda.amazonaws.com}, Action: sts:AssumeRole}]}
      ManagedPolicyArns: [arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole]
      Policies:
        - PolicyName: interceptor
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - {Effect: Allow, Action: dynamodb:UpdateItem, Resource: !GetAtt RateTable.Arn}
              - {Effect: Allow, Action: ssm:GetParameter, Resource: !Sub "arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/dezerv/freeze"}
              - {Effect: Allow, Action: [logs:CreateLogStream, logs:PutLogEvents], Resource: !Sub "${GatewayAuditLogs.Arn}:*"}
'''
body = ""
for n, f in fns.items():
    role = "InterceptorRole" if n == "interceptor" else "ToolRole"
    env = "".join(f"\n          {k}: {v if v.startswith('!') else chr(34)+v+chr(34)}" for k, v in f["env"].items())
    envblock = f"\n      Environment:\n        Variables:{env}" if env else ""
    body += f'''  {n.capitalize()}Fn:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: dezerv-laba-{n}
      Runtime: python3.12
      Handler: handler.lambda_handler
      Role: !GetAtt {role}.Arn
      Timeout: {f["t"]}
      MemorySize: {f["mem"]}
      Code: {{S3Bucket: !Ref ArtifactBucket, S3Key: !Sub "lambda/{n}-${{CodeHash}}.zip"}}{envblock}
'''
tail = r'''  GatewayRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub dezerv-laba-gateway-${AWS::Region}
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement: [{Effect: Allow, Principal: {Service: bedrock-agentcore.amazonaws.com}, Action: sts:AssumeRole, Condition: {StringEquals: {"aws:SourceAccount": !Ref "AWS::AccountId"}}}]
      Policies:
        - PolicyName: invoke
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - {Effect: Allow, Action: lambda:InvokeFunction, Resource: !Sub "arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:dezerv-laba-*"}
              - Effect: Allow
                Action: [bedrock-agentcore:AuthorizeAction, bedrock-agentcore:PartiallyAuthorizeActions, bedrock-agentcore:GetPolicyEngine]
                Resource:
                  - !Sub "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:policy-engine/*"
                  - !Sub "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:gateway/*"
  AgentRuntimeRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub dezerv-laba-runtime-${AWS::Region}
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement: [{Effect: Allow, Principal: {Service: bedrock-agentcore.amazonaws.com}, Action: sts:AssumeRole, Condition: {StringEquals: {"aws:SourceAccount": !Ref "AWS::AccountId"}}}]
      Policies:
        - PolicyName: runtime
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - {Effect: Allow, Action: [bedrock:InvokeModel, bedrock:InvokeModelWithResponseStream], Resource: ["arn:aws:bedrock:*::foundation-model/*", !Sub "arn:aws:bedrock:*:${AWS::AccountId}:inference-profile/*"]}
              - {Effect: Allow, Action: [logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents, logs:DescribeLogStreams], Resource: [!Sub "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/*", !Sub "${AgentAuditLogs.Arn}:*"]}
              - {Effect: Allow, Action: [bedrock-agentcore:RetrieveMemoryRecords, bedrock-agentcore:ListMemoryRecords], Resource: !Sub "arn:aws:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:memory/*"}
              - {Effect: Allow, Action: [bedrock-agentcore:GetWorkloadAccessToken, bedrock-agentcore:GetWorkloadAccessTokenForJWT, bedrock-agentcore:GetWorkloadAccessTokenForUserId], Resource: "*"}
              - {Effect: Allow, Action: [xray:PutTraceSegments, xray:PutTelemetryRecords], Resource: "*"}
              - {Effect: Allow, Action: cloudwatch:PutMetricData, Resource: "*", Condition: {StringEquals: {"cloudwatch:namespace": bedrock-agentcore}}}
              - {Effect: Allow, Action: s3:GetObject, Resource: !Sub "arn:aws:s3:::dezerv-laba-artifacts-${AWS::AccountId}-${AWS::Region}/*"}
  UserPool:
    Type: AWS::Cognito::UserPool
    Properties: {UserPoolName: dezerv-laba, Policies: {PasswordPolicy: {MinimumLength: 12}}}
  UserPoolDomain:
    Type: AWS::Cognito::UserPoolDomain
    Properties: {Domain: !Sub "dezerv-laba-${AWS::AccountId}", UserPoolId: !Ref UserPool}
  ResourceServer:
    Type: AWS::Cognito::UserPoolResourceServer
    Properties:
      UserPoolId: !Ref UserPool
      Identifier: payments
      Name: payments
      Scopes:
        - {ScopeName: logs.read, ScopeDescription: read logs}
        - {ScopeName: db.read, ScopeDescription: read transactions}
        - {ScopeName: warehouse.read, ScopeDescription: read warehouse}
        - {ScopeName: changes.read, ScopeDescription: read deploys}
        - {ScopeName: tickets.read, ScopeDescription: read tickets}
        - {ScopeName: tickets.write, ScopeDescription: write tickets}
        - {ScopeName: mandates.read, ScopeDescription: read mandates (Lab B Go tool)}
        - {ScopeName: custom.read, ScopeDescription: read squad custom tools (capstone)}
  OncallClient:
    Type: AWS::Cognito::UserPoolClient
    DependsOn: ResourceServer
    Properties:
      UserPoolId: !Ref UserPool
      ClientName: oncall
      GenerateSecret: true
      AllowedOAuthFlowsUserPoolClient: true
      AllowedOAuthFlows: [client_credentials]
      AllowedOAuthScopes: [payments/logs.read, payments/db.read, payments/warehouse.read, payments/changes.read, payments/tickets.read, payments/tickets.write, payments/mandates.read, payments/custom.read]
  SupportClient:
    Type: AWS::Cognito::UserPoolClient
    DependsOn: ResourceServer
    Properties:
      UserPoolId: !Ref UserPool
      ClientName: support
      GenerateSecret: true
      AllowedOAuthFlowsUserPoolClient: true
      AllowedOAuthFlows: [client_credentials]
      AllowedOAuthScopes: [payments/tickets.read, payments/tickets.write]
Outputs:
  DataBucket: {Value: !Ref DataBucket}
  GatewayRoleArn: {Value: !GetAtt GatewayRole.Arn}
  RuntimeRoleArn: {Value: !GetAtt AgentRuntimeRole.Arn}
  ToolRoleArn: {Value: !GetAtt ToolRole.Arn}
  UserPoolId: {Value: !Ref UserPool}
  DiscoveryUrl: {Value: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/${UserPool}/.well-known/openid-configuration"}
  TokenUrl: {Value: !Sub "https://dezerv-laba-${AWS::AccountId}.auth.${AWS::Region}.amazoncognito.com/oauth2/token"}
  OncallClientId: {Value: !Ref OncallClient}
  SupportClientId: {Value: !Ref SupportClient}
'''
for n in fns:
    tail += f"  {n.capitalize()}FnArn: {{Value: !GetAtt {n.capitalize()}Fn.Arn}}\n"
open("infra/template.yaml", "w").write(head + body + tail)
