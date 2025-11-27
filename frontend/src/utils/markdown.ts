import DOMPurify from 'dompurify'
import { marked, Renderer } from 'marked'

const renderer = new Renderer()

renderer.link = (href, title, text) => {
  const safeHref = typeof href === 'string' ? href.trim() : ''
  const display = text || href || ''
  const titleAttr = title ? ` title="${title}"` : ''
  if (!safeHref) {
    return display
  }
  return `<a href="${safeHref}"${titleAttr} target="_blank" rel="noopener noreferrer">${display}</a>`
}

marked.setOptions({
  gfm: true,
  breaks: true,
  renderer,
})

export function renderMarkdown(text: string | null | undefined): string {
  if (!text) return ''
  const html = marked.parse(text)
  const sanitized = DOMPurify.sanitize(typeof html === 'string' ? html : '')
  return sanitized
}
