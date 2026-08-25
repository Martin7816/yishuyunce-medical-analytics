const HTML_ESCAPE_PATTERN = /[&<>"'\u0000]/g
const HTML_ENTITIES = Object.freeze({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
  '\u0000': '\uFFFD',
})

const TOKEN_PREFIX = '\u0000markdown-token-'
const TOKEN_SUFFIX = '\u0001'

function escapeHtml(value) {
  return String(value).replace(HTML_ESCAPE_PATTERN, character => HTML_ENTITIES[character])
}

function renderInline(value) {
  const tokens = []
  const storeToken = html => {
    const index = tokens.push(html) - 1
    return `${TOKEN_PREFIX}${index}${TOKEN_SUFFIX}`
  }

  let source = escapeHtml(value)
  source = source.replace(/`([^`\n]+)`/g, (_, content) => storeToken(`<code>${content}</code>`))
  source = source.replace(/\*\*([^*\n]+)\*\*/g, (_, content) => storeToken(`<strong>${content}</strong>`))
  source = source.replace(/__([^_\n]+)__/g, (_, content) => storeToken(`<strong>${content}</strong>`))
  source = source.replace(/\*([^*\n]+)\*/g, (_, content) => storeToken(`<em>${content}</em>`))
  source = source.replace(/_([^_\n]+)_/g, (_, content) => storeToken(`<em>${content}</em>`))

  const tokenPattern = new RegExp(`${TOKEN_PREFIX}(\\d+)${TOKEN_SUFFIX}`, 'g')
  return source
    .replace(tokenPattern, (_, index) => tokens[Number(index)] || '')
    .replace(/\n/g, '<br>')
}

function splitTableRow(line) {
  let row = line.trim()
  if (row.startsWith('|')) row = row.slice(1)
  if (row.endsWith('|') && !row.endsWith('\\|')) row = row.slice(0, -1)
  return row.split('|').map(cell => cell.trim())
}

function isTableSeparator(line) {
  const cells = splitTableRow(line)
  return cells.length > 1 && cells.every(cell => /^:?-{2,}:?$/.test(cell))
}

function isTableStart(lines, index) {
  return Boolean(
    lines[index]?.includes('|')
      && lines[index + 1]?.includes('|')
      && isTableSeparator(lines[index + 1]),
  )
}

function renderTable(headers, rows) {
  const headerMarkup = headers
    .map(header => `<th scope="col">${renderInline(header)}</th>`)
    .join('')
  const bodyMarkup = rows
    .map(row => {
      const cells = headers.map((_, index) => row[index] || '')
      return `<tr>${cells.map(cell => `<td>${renderInline(cell)}</td>`).join('')}</tr>`
    })
    .join('')

  return [
    '<div class="answer-markdown-table-wrap">',
    '<table class="answer-markdown-table">',
    `<thead><tr>${headerMarkup}</tr></thead>`,
    bodyMarkup ? `<tbody>${bodyMarkup}</tbody>` : '',
    '</table>',
    '</div>',
  ].join('')
}

function fenceInfo(line) {
  const match = line.match(/^\s{0,3}(`{3,}|~{3,})/)
  if (!match) return null
  return { character: match[1][0], length: match[1].length }
}

function isFenceEnd(line, fence) {
  const pattern = new RegExp(`^\\s{0,3}${fence.character}{${fence.length},}\\s*$`)
  return pattern.test(line)
}

function isHeading(line) {
  return line.match(/^\s{0,3}(#{1,6})[ \t]+(.+?)\s*$/)
}

function isUnorderedItem(line) {
  return line.match(/^\s{0,3}[-+*][ \t]+(.+)$/)
}

function isOrderedItem(line) {
  return line.match(/^\s{0,3}\d+[.)][ \t]+(.+)$/)
}

function isBlockquote(line) {
  return /^\s{0,3}>[ \t]?/.test(line)
}

function isHorizontalRule(line) {
  return /^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)
}

function renderList(lines, ordered) {
  const tag = ordered ? 'ol' : 'ul'
  const items = lines.map(line => {
    const match = ordered ? isOrderedItem(line) : isUnorderedItem(line)
    return `<li>${renderInline(match ? match[1] : '')}</li>`
  }).join('')
  return `<${tag}>${items}</${tag}>`
}

/**
 * Render the small Markdown subset accepted from the model.
 * All model text is escaped first; generated tags and attributes are fixed
 * literals, so this function never passes raw model HTML to v-html.
 */
export function renderSafeMarkdown(markdown) {
  if (typeof markdown !== 'string' || !markdown) return ''

  const lines = markdown.replace(/\r\n?/g, '\n').split('\n')
  const blocks = []
  let paragraph = []

  const flushParagraph = () => {
    const text = paragraph.join('\n').trim()
    if (text) blocks.push(`<p>${renderInline(text)}</p>`)
    paragraph = []
  }

  let index = 0
  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      flushParagraph()
      index += 1
      continue
    }

    const fence = fenceInfo(line)
    if (fence) {
      flushParagraph()
      const codeLines = []
      index += 1
      while (index < lines.length && !isFenceEnd(lines[index], fence)) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    const heading = isHeading(line)
    if (heading) {
      flushParagraph()
      const level = heading[1].length
      const content = heading[2].replace(/[ \t]+#+[ \t]*$/, '').trim()
      blocks.push(`<h${level}>${renderInline(content)}</h${level}>`)
      index += 1
      continue
    }

    if (isTableStart(lines, index)) {
      flushParagraph()
      const headers = splitTableRow(lines[index])
      index += 2
      const rows = []
      while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }
      blocks.push(renderTable(headers, rows))
      continue
    }

    if (isBlockquote(line)) {
      flushParagraph()
      const quoteLines = []
      while (index < lines.length && isBlockquote(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s{0,3}>[ \t]?/, ''))
        index += 1
      }
      blocks.push(`<blockquote>${renderSafeMarkdown(quoteLines.join('\n'))}</blockquote>`)
      continue
    }

    if (isUnorderedItem(line)) {
      flushParagraph()
      const listLines = []
      while (index < lines.length && isUnorderedItem(lines[index])) {
        listLines.push(lines[index])
        index += 1
      }
      blocks.push(renderList(listLines, false))
      continue
    }

    if (isOrderedItem(line)) {
      flushParagraph()
      const listLines = []
      while (index < lines.length && isOrderedItem(lines[index])) {
        listLines.push(lines[index])
        index += 1
      }
      blocks.push(renderList(listLines, true))
      continue
    }

    if (isHorizontalRule(line)) {
      flushParagraph()
      blocks.push('<hr>')
      index += 1
      continue
    }

    paragraph.push(line)
    index += 1
  }

  flushParagraph()
  return blocks.join('')
}
