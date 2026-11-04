# AWS 部署（ECS Fargate + Amazon Bedrock）

本文件說明如何把後端從 Render 搬到 AWS，並把 LLM／embedding 從 Azure OpenAI 換成 Amazon Bedrock。
前端（Firebase Hosting、Firebase Auth）、PostgreSQL（Neon）、Qdrant Cloud、Cloudinary 維持原樣。
一般的環境變數與本地開發請見 [deployment.md](deployment.md)。

> ⚠️ 本文件與其中的範本**尚未在真實 AWS 帳號上驗證**：CloudFormation 範本只通過 `cfn-lint`，
> Bedrock 轉接層只有以假的 client 做單元測試。第一次部署請依下方「驗證清單」逐項確認。

---

## 架構

```
使用者 ─► Firebase Hosting（前端，不變）
              │  VITE_API_URL=https://<你的 API 網域>/api
              ▼
        ALB（HTTPS, idle timeout 900s）
              ▼
   ECS Fargate × 1 task（FastAPI, 單 worker）──► Amazon Bedrock（Claude / Titan，經 task role）
              ├──► Neon PostgreSQL（DATABASE_URL）
              ├──► Qdrant Cloud（QDRANT_URL）
              └──► Cloudinary（PDF）
```

為什麼只能 1 個 task：PDF 問答的 stream lock／cancel／steering 存在 process 記憶體內（見
`backend/app/main.py`），多個 task 或多個 worker 會互相看不到。所以 CloudFormation 的
`DesiredCount` 只允許 0 或 1。

為什麼 ALB idle timeout 設 900 秒：研究型 agent 單一節點最長可跑 600 秒；SSE 每 15 秒會送一次心跳，
連線不會被視為閒置，但保守起見仍把上限放寬（App Runner 有約 120 秒的請求上限，因此不採用）。

---

## 1. 在 Bedrock 開通模型

1. AWS Console 切到 **ap-northeast-1（東京）** → Amazon Bedrock → Model access，申請 Claude（Sonnet 與 Haiku）
   與 **Titan Text Embeddings V2**。Anthropic 模型首次使用需填寫使用案例表單。
2. 到 Bedrock → Cross-region inference，記下要使用的 **inference profile ID**（APAC 開頭，例如
   `apac.anthropic.claude-…`）。實際可用的模型與 ID 以你帳號畫面為準，**請勿照抄範例**。
3. 之後填入：
   - `BEDROCK_CHAT_MODEL_ID`：主要對話模型（課程助理、PDF 問答主 agent、研究 agent）
   - `BEDROCK_MINI_MODEL_ID`：輕量模型（router、單課問答、使用者側寫），留空則沿用主要模型

> ⚠️ **模型必須支援 structured outputs 與 strict tool use。** PDF 問答大量使用結構化輸出
> （`ProviderStrategy(..., strict=True)`、`with_structured_output(..., strict=True)`），`langchain-aws` 會把它們翻成
> Converse 的 `outputConfig.textFormat` json_schema 與 `toolSpec.strict`。這兩項只有部分較新的 Claude 型號支援，
> **主要模型與輕量模型（Haiku）都必須支援**，請在 Bedrock 文件確認所選型號；不支援時 PDF 問答與研究 agent 會失敗。
> 另外，送進結構化輸出的 schema 不可含 `maxItems`、`minLength`、`minimum` 等約束；
> `backend/tests/test_structured_output_and_store.py` 會檢查這點。
> `langchain-aws` 與 `boto3` 已在 `requirements.txt` 鎖定實測版本，請勿隨意升級。

## 2. 重建向量索引（必要）

Titan V2 最高 1024 維，原本的 text-embedding-3-large 是 3072 維，**所有 Qdrant collection 都必須重新向量化**，
舊向量不能混用。建議建在**新的 collection／新的 cluster**，驗證後再切換，舊資料保留可隨時回滾。

需要可呼叫 Bedrock 的本機憑證（`aws configure sso`，並設定 `AWS_PROFILE`、`AWS_REGION=ap-northeast-1`），
以及 `.env` 內的 `BEDROCK_*`、`QDRANT_URL`、`QDRANT_API_KEY`。

| Collection | 重建方式 |
|---|---|
| `ncu_courses_ug` / `ncu_courses_grad` / `ncu_credit_programs` / `ncu_departments` / `ncu_teachers` | `python scripts/rag/build_vector_index.py --reset` |
| `ncu_graph_nodes` | `python scripts/rag/build_qdrant_index.py --reset`，再執行 `python scripts/rag/add_communities_to_qdrant.py` |
| PDF 研究計畫 `reports` | `python scripts/rag/reembed_qdrant_collection.py reports --text-field page_content --dry-run` 確認結構，去掉 `--dry-run` 後寫入新 collection `reports_titan1024`；後端用 `PDF_QDRANT_COLLECTION=reports_titan1024` 指向它 |

注意：
- `--reset` 會清空**目前 `QDRANT_URL` 指向的 collection**。要保留舊資料，請先另建一個 Qdrant cluster（或先用
  `scripts/rag/migrate_qdrant_to_cloud.py` 備份），並讓 `.env` 的 `QDRANT_URL` 指向新的 cluster。
- 課程查詢快取 collection（`ncu_query_embedding_cache`）會由後端在第一次使用時以新維度自動建立；若舊維度的同名
  collection 已存在，請先刪除它。
- `reports` 的文字欄位名稱（`page_content`）是 LangChain 預設值，請先用 `--dry-run` 確認；該 collection 原本的建索引
  流程不在這個 repo 內。
- 重新向量化後請抽樣檢查檢索品質（見驗證清單），Titan 與 text-embedding-3-large 的中文檢索表現不會完全相同。

### 2.1 遷移 Postgres 的 LangGraph store（必要）

PDF 問答的長期記憶與使用者側寫存在 Neon 的 `store_vectors` 表，欄位是 `vector(3072)`。
`AsyncPostgresStore.setup()` 使用 `CREATE TABLE IF NOT EXISTS`，**不會**改既有表的維度，所以換成 1024 維後，
寫入與搜尋會失敗，而相關呼叫的例外都被吞掉（只剩 warning），功能會「靜默失效」。後端啟動時會檢查維度，
不一致就在日誌記一筆 `store_vectors.embedding 維度為 …` 的 error。

這些記憶可以重建，直接清空即可（在 Neon SQL editor 執行）：

```sql
TRUNCATE store_vectors;
DROP INDEX IF EXISTS store_vectors_embedding_idx;
ALTER TABLE store_vectors ALTER COLUMN embedding TYPE vector(1024);
```

之後重新啟動服務，索引會重建。

**不要讓 Render（舊 3072 維）與 AWS（新 1024 維）共用同一個資料庫**：兩邊對 `store_vectors` 的維度要求互相衝突。
並行期請替 AWS 另建一個 Neon branch／資料庫（`DATABASE_URL` 指向它），或接受 Render 的記憶功能暫時失效。

## 3. 建立 Secrets Manager 密鑰

Console → Secrets Manager → Store a new secret → **Other type of secret**，用 JSON 填入下列 key（區域同樣是東京）：

```json
{
  "DATABASE_URL": "postgresql://…",
  "QDRANT_URL": "https://…",
  "QDRANT_API_KEY": "…",
  "CLOUDINARY_CLOUD_NAME": "…",
  "CLOUDINARY_API_KEY": "…",
  "CLOUDINARY_API_SECRET": "…",
  "FIREBASE_SERVICE_ACCOUNT_JSON": "{…整份 service account JSON 當成字串…}",
  "DEVELOPER_EMAILS": "a@example.com,b@example.com"
}
```

記下這個密鑰的**完整 ARN**（結尾含 `-xxxxxx` 六碼隨機字尾；CloudFormation 的 `ValueFrom` 需要完整 ARN）。LangSmith 為選填，需要時自行在 task definition 追加 `LANGSMITH_API_KEY` 等 secret。

## 4. 準備網域與憑證

瀏覽器從 HTTPS 的 Firebase 前端呼叫 API，API 必須是 HTTPS（否則會被 mixed content 擋下）。

1. 準備一個 API 網域（例如 `api.example.com`）。
2. 在東京區域的 ACM 申請該網域的憑證並完成 DNS 驗證，記下憑證 ARN。

## 5. 部署 CloudFormation

Console → CloudFormation → Create stack → Upload `deploy/aws/ecs-fargate.yaml`。主要參數：

| 參數 | 說明 |
|---|---|
| `VpcId` / `PublicSubnetIds` | 預設 VPC 即可；至少選 2 個不同 AZ 的公有子網路 |
| `CertificateArn` | 步驟 4 的憑證 |
| `SecretArn` | 步驟 3 的密鑰 |
| `BedrockChatModelId` / `BedrockMiniModelId` | 步驟 1 的 ID |
| `PdfQdrantCollection` | 重建後的 PDF collection 名稱 |
| `DesiredCount` | **第一次保持 0**（此時 ECR 還沒有映像） |

建好後：

1. 在 DNS 建立 `api.example.com` → Outputs 的 `LoadBalancerDnsName`（CNAME 或 Route 53 alias）。
2. 推送第一個映像（任選一種）：
   - 在本機執行（需先 `aws configure sso`）：
     ```bash
     aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin <帳號>.dkr.ecr.ap-northeast-1.amazonaws.com
     docker build -t <RepositoryUri>:latest .
     docker push <RepositoryUri>:latest
     ```
   - 或先完成步驟 6 再用 GitHub Actions。
3. 更新 stack，把 `DesiredCount` 改為 **1**。之後每次更新 stack 都要保留這個值（Console 選 *Use existing value*），
   否則預設的 0 會把服務縮成 0 個 task。
4. GitHub Actions 部署會用 `register-task-definition` 建立新的 revision，與 CloudFormation 管理的 task definition
   會產生 drift；之後若再更新 stack 且改到 task definition，請先確認使用的映像標籤。

## 6. 讓 GitHub Actions 部署（選用）

1. 部署 `deploy/aws/github-oidc-deploy-role.yaml`：`ExecutionRoleArn`、`TaskRoleArn` 填入 `ecs-fargate` stack 的 Outputs
   （`iam:PassRole` 只會授權給這兩個角色）；若帳號已有 GitHub OIDC provider，`CreateOidcProvider` 選 false 並填入其 ARN。
2. 把 Outputs 的 `DeployRoleArn` 設為 GitHub repo secret `AWS_DEPLOY_ROLE_ARN`。
3. Actions → **Deploy backend to AWS ECS Fargate** → Run workflow。流程：建置映像、推到 ECR、以新映像註冊
   task definition、更新服務並等待穩定。只允許 `main` 分支且 repo 為 `ChiJiun/NCU_AI_Guidance`。

## 7. 切換前端

1. 更新 GitHub secret `VITE_API_URL=https://api.example.com/api`，重新部署前端（push 到 `main` 會觸發 Firebase workflow）。
2. Firebase Auth 不需要改程式碼（`signInWithPopup`，授權網域是前端網域，沒有變）。
3. CORS：`AllowedOrigins` 參數需包含前端網域。
4. 建議讓 Render 與 AWS 並行一段時間，確認穩定再停掉 Render。並行時兩邊必須使用**不同的 Qdrant collection**
   （Render：舊的 3072 維；AWS：新的 1024 維）與**不同的 Postgres 資料庫**（見 2.1），不能共用。

---

## 驗證清單

部署後依序確認：

- [ ] `https://api.example.com/health` 回 `{"status":"healthy"}`；`/ready` 回 200
- [ ] ECS 任務 Running，CloudWatch Logs `/ecs/ncu-ai-guidance-backend` 沒有 `AccessDeniedException`／`ValidationException`
- [ ] 課程助理（`/course-search`）提一個需要呼叫工具的問題，確認：串流逐字輸出、有 `tool_start` 事件、最後有課程卡片
- [ ] 課程資訊頁的單課問答可回答
- [ ] PDF 問答：簡單問題（chat agent）與複雜問題（research agent，可能超過 2 分鐘）都能完整串流結束
- [ ] 監控頁 `/monitor` 的模型名稱與 token 數正常
- [ ] 抽樣比較重建索引前後的檢索結果（例如固定 10 題），確認品質沒有明顯退步

## 已知差異與風險

- **模型行為不同**：prompt 是針對 gpt-4o 調過的，改用 Claude 後工具呼叫順序、回答風格、JSON 結構化輸出可能有差異，
  需要實際測試並視情況調整 prompt。
- **平行工具呼叫**：原本 PDF agent 以 `parallel_tool_calls=False` 限制一次一個工具呼叫；Bedrock Converse 沒有對應參數，
  現在不再限制。若發現工具共享狀態造成問題，需在 agent 層處理。
- **LangSmith**：課程助理不再包裝 OpenAI client，LLM 追蹤改為函式層級（`@traceable`），不是每次模型請求；PDF 問答的
  LangChain 追蹤不受影響。
- **費用估算**：監控頁的費用是估算，預設值沿用 Azure 時期的單價；請依實際模型價目設定
  `COURSE_PRICE_*` / `PDF_AGENT_PRICE_*` / `PDF_ROUTER_PRICE_*`。
- **其他一次性腳本**：`scripts/nlp/`、`scripts/extraction/`、`scripts/graph/label_communities.py`、
  `scripts/test_course_agent/test_retrieval_layers.py` 這些離線資料處理／測試腳本
  仍使用 Azure／OpenAI，不影響線上服務；需要時再另行遷移。
- **部署行為**：滾動更新（最小 100%／最大 200%）時，新舊兩個 task 會短暫並存，process 內的 stream lock／cancel 在這段時間
  不一致；`StopTimeout` 已設為 Fargate 上限 120 秒，但進行中的長時間研究串流仍可能在換版時被中斷。要嚴格單 task，
  可把 `MinimumHealthyPercent` 改 0／`MaximumPercent` 改 100，代價是換版期間短暫停機。
- **冷啟動**：映像沒有預先下載 fastembed／flashrank 模型，每個新 task 啟動時會從網路下載，首次健康檢查可能較慢
  （已設 `HealthCheckGracePeriodSeconds: 120`）。
- **輸出長度**：LangChain 路徑沒有明確設定 `max_tokens`，長度取決於模型預設值；若回答被截斷再補設定。
- **監控頁型號顯示**：`response_metadata["model_name"]` 在 Bedrock 下可能為空，監控頁的 agent 型號可能顯示空白。
- **成本**：Fargate（2 vCPU / 8 GB）＋ ALB 是固定費用；觀察 CloudWatch 的 CPU／記憶體後可調降 `TaskCpu`／`TaskMemory`。
- **回滾**：CloudFormation 啟用了 deployment circuit breaker；也可把 `PDF_QDRANT_COLLECTION`／Render 切回舊設定。
