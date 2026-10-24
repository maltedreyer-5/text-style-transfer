# Two paths: neutral intermediate text or direct

## Decision

The application offers two ways from the source text to the target style: through a neutral
intermediate text, and directly.

## Reasons

When a model removes an existing style and adds a new one in a single step, features of the source,
such as irony, slang or academic jargon, tend to persist in the result. The neutral path separates the
two tasks. Neutralisation is restricted to the selected dimensions and has three depths of
intervention, so that only the selected features are removed.

The direct path requires one model call instead of two. It keeps those features of the source that
the target style does not address.

The neutral text is shown and can be edited. It is stored per session under a hash of text, text
language and neutralisation settings. While these remain unchanged, the stored or edited neutral text
is reused, so that several target styles can be compared with a single neutralisation.

## Rules for both paths

The instructions to the model contain the same rules on both paths:

- Quotations, numbers, names, dates and units remain unchanged.
- The result contains no facts, examples, evaluations, conclusions or sentences that the source does
  not contain. Evaluations and conclusions are named explicitly, because models tend to add paragraphs
  of commentary when a style is pronounced.
- The target length is stated in words. A number of words steers the length more reliably than terms
  such as "short" or "long".
- Features are listed in descending strength, each with a description of its dosage. Without such a
  description, adjacent strengths such as "light" and "moderate" produce no difference.

## Limits

- Neutralisation can remove nuances that the target style would have kept. The direct path exists for
  this case.
- The rule against additions is an instruction to the model. The checks for length, numbers and
  quotations detect the most frequent violations; they do not detect every addition.
