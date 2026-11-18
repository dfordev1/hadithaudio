const { Readable } = require('node:stream');
const { pipeline } = require('node:stream/promises');

const files = new Map([
  ['aqidah-tahawiyyah', 'ar_Al3qedh_AlT7aweh_AlAnsaree.mp3'],
  ['alfiyyah-ibn-malik', 'ar_Alfeyyat_Ibn_Malek_Nashmi.mp3'],
]);
const base = 'https://github.com/playorbitt/arabic-word-reader/releases/download/Audios/';

module.exports = async function audio(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('Allow', 'GET, HEAD');
    return res.status(405).end();
  }
  const file = files.get(req.query.book);
  if (!file) return res.status(404).end();
  const range = req.headers.range;
  if (range && !/^bytes=(?:\d+-\d*|-\d+)$/.test(range)) return res.status(416).end();

  const abort = new AbortController();
  const onClose = () => { if (!res.writableFinished) abort.abort(); };
  res.once('close', onClose);
  try {
    const upstream = await fetch(base + file, {
      method: req.method,
      headers: range ? { range } : {},
      signal: abort.signal,
    });
    if (!upstream.ok && upstream.status !== 416) {
      await upstream.body?.cancel();
      return res.status(502).end();
    }
    for (const name of ['content-range', 'content-length', 'accept-ranges']) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.status(upstream.status);
    res.setHeader('Content-Type', 'audio/mpeg');
    if (upstream.status === 200 || upstream.status === 206) res.setHeader('Cache-Control', 'public, max-age=3600');
    if (!upstream.body) return res.end();
    await pipeline(Readable.fromWeb(upstream.body), res);
  } catch {
    if (!res.headersSent && !res.destroyed) res.status(502).end();
  } finally {
    res.off('close', onClose);
  }
};
