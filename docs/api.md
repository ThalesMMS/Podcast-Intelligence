# REST API

The complete specification is generated at `/openapi.json` and displayed at
`/docs`.

## Main endpoints

| Method | Route | Purpose |
|---|---|---|
| POST | `/v1/uploads` | Create a presigned URL for direct upload |
| POST | `/v1/imports` | Create an episode and asynchronous job |
| GET | `/v1/jobs/{id}` | Read progress and steps |
| POST | `/v1/jobs/{id}/cancel` | Request cancellation |
| POST | `/v1/jobs/{id}/retry` | Resume a failed/cancelled job |
| GET | `/v1/episodes` | List the library |
| GET | `/v1/episodes/{id}` | Get details, summary, playback, and job |
| GET | `/v1/episodes/{id}/playback` | Renew a private playback URL |
| GET | `/v1/episodes/{id}/transcript` | Get timed segments |
| PATCH | `/v1/episodes/{id}/speakers/{speaker_id}` | Confirm a speaker name |
| POST | `/v1/episodes/{id}/summaries` | Create/regenerate a summary |
| GET | `/v1/episodes/{id}/exports/{format}` | Export JSON, Markdown, SRT, or VTT |
| POST | `/v1/search` | Hybrid search |
| POST | `/v1/conversations` | Create an episode chat |
| POST | `/v1/conversations/{id}/messages` | Ask a question with citations |
| GET | `/v1/providers` | Inspect configured capabilities |

## RSS import example

```json
{
  "source": {
    "type": "rss",
    "url": "https://example.org/feed.xml",
    "episode_title": "Optional title to match"
  },
  "options": {
    "language": "pt",
    "diarization": true,
    "generate_summary": true
  }
}
```

The HTTP 202 response contains `episode_id` and `job_id`. The client follows the
job by polling; SSE can be added without changing persisted states.

## Private playback

Episode details include `playback_url` and `playback_expires_at`. The frontend
renews the signature before that time through `GET /v1/episodes/{id}/playback`,
which revalidates the workspace and returns `playback_url`, `expires_at`, and
`expires_in`. Configure the duration with `PLAYBACK_URL_EXPIRES_SECONDS`
(default: 900 seconds).

The opt-in test `tests/test_playback_s3.py` covers expiration, renewal, and
`Range` requests in S3/MinIO. Set `TEST_S3_ENDPOINT_URL`,
`TEST_S3_ACCESS_KEY`, `TEST_S3_SECRET_KEY`, and `TEST_S3_BUCKET`; optionally set
`TEST_S3_PUBLIC_ENDPOINT_URL` and `TEST_S3_REGION`.

## Input limits

- episode titles (`episode_title`, `title_override`, and `filename` during
  import): 1,000 characters;
- conversation title: 500 characters;
- confirmed speaker name: 300 characters;
- external episode GUID: 500 characters;
- MIME type: 255 characters;
- language: a BCP 47 code of up to 32 characters. `_` separators are converted
  to `-` and capitalization is normalized; for example, `PT_br` becomes
  `pt-BR`.

Values above these limits or invalid language codes return HTTP 422 before
persistence and queueing.

## Upload

1. `POST /v1/uploads` with name, MIME type, and size.
2. Multipart `POST` of the file to `upload_url`, including every returned
   `fields` value and the binary in the `file` field. The S3/MinIO policy limits
   size to the declared value and binds the MIME type.
3. `POST /v1/imports` with `source.type=upload` and `object_key`.

The backend never accepts a client-supplied local path. Before processing the
object, the pipeline also compares its stored size with the signed metadata.
