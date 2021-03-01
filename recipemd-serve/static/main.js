let controller


const yieldInput = document.getElementById("yield")
const yieldCompletions = document.getElementById("yield_completions")
const content = document.getElementById("content")

function updateCompletions(value) {
    const valueParts = value.split(" ")
    const lastPart = valueParts[valueParts.length - 1]

    const prefixUnit = units.find(unit => unit.toLowerCase().indexOf(lastPart.toLowerCase()) == 0)

    const completionBaseParts = prefixUnit ? valueParts.slice(0, valueParts.length - 1) : valueParts
    const completions = [[...completionBaseParts].join(" ")]
    for (const unit of units) {
        completions.push([...completionBaseParts, unit].join(" "))
    }

    yieldCompletions.innerHTML = completions.map(compl => `<option value="${compl}" />`).join("")

}

async function fetchYield(value) {
    if (controller) {
        controller.abort()
    }

    const url = new URL(location.href)
    url.searchParams.delete('yield')
    url.searchParams.append('yield', value)

    controller = new AbortController()
    const responsePromise = fetch(url.href, {
        signal: controller.signal,
        headers: {
         "X-PJAX": true
        }
    })

    let response
    try {
        response = await responsePromise
    } catch (e) {
        if (e.name === 'AbortError') {
            return
        }
        throw e
    }

    content.innerHTML = await response.text()
}

if (yieldInput) {
   yieldInput.addEventListener("keyup", (e) => {
        updateCompletions(e.target.value)
        fetchYield(e.target.value)
    })

    updateCompletions("1")
}
