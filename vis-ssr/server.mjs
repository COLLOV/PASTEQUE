import 'dotenv/config';
import express from 'express';
import { render } from '@antv/gpt-vis-ssr';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

const DEFAULT_OUT_SUBDIR = 'charts';

const resolvePort = () => {
  const value = process.env.GPT_VIS_SSR_PORT;
  if (!value) {
    throw new Error('GPT_VIS_SSR_PORT is required to start the SSR server');
  }

  if (!/^\d+$/.test(value)) {
    throw new Error(`Invalid GPT_VIS_SSR_PORT "${value}" (must be numeric)`);
  }

  const parsed = Number.parseInt(value, 10);
  if (parsed <= 0 || parsed >= 65536) {
    throw new Error(`GPT_VIS_SSR_PORT "${value}" out of range (1-65535)`);
  }

  return parsed;
};

const port = resolvePort();
const outputDir = resolve(
  process.env.VIS_IMAGE_DIR || join(process.cwd(), DEFAULT_OUT_SUBDIR),
);

mkdirSync(outputDir, { recursive: true });

const handleFatal = (event, error) => {
  console.error(`[vis-ssr] ${event}`, error);
  process.exit(1);
};

process.on('unhandledRejection', (error) => handleFatal('unhandled-rejection', error));
process.on('uncaughtException', (error) => handleFatal('uncaught-exception', error));

const app = express();
app.use(express.json({ limit: '1mb' }));

app.get('/health', (_req, res) => {
  res.json({ ok: true });
});

const handleGenerate = async (req, res) => {
  let vis = null;

  try {
    vis = await render(req.body);
    const png = vis.toBuffer();
    const name = `chart_${Date.now()}_${randomUUID()}.png`;
    const filePath = join(outputDir, name);

    writeFileSync(filePath, png);
    vis.destroy();
    vis = null;

    const url = `http://localhost:${port}/charts/${name}`;
    console.info('[vis-ssr] generated chart', { url, filePath });

    res.json({ success: true, url, resultObj: url });
  } catch (error) {
    console.error('[vis-ssr] render failed', error);
    res
      .status(500)
      .json({ success: false, error: error instanceof Error ? error.message : String(error) });
  } finally {
    if (vis) {
      try {
        vis.destroy();
      } catch (destroyError) {
        console.warn('[vis-ssr] failed to destroy vis instance', destroyError);
      }
    }
  }
};

app.post('/', handleGenerate);
app.post('/generate', handleGenerate);

app.use('/charts', express.static(outputDir));

app.listen(port, () => {
  console.info(
    `[vis-ssr] server listening on http://localhost:${port} with output directory ${outputDir}`,
  );
});
