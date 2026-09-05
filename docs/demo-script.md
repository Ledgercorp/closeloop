# Demo Script Draft

Target runtime: 2:50–2:55.

1. User: "Alexa, cancel my StreamBox subscription before it renews tomorrow. Don't tell me it's done until you can prove it."
2. Alexa confirms the consequential action.
3. Healthy run: provider changes state; independent verifier reads auto-renew OFF; result = Verified.
4. Fault injection: provider reports cancellation success but leaves auto-renew ON; result = Not completed.
5. Evidence outage: cancellation request is sent but independent read-back is unavailable; result = Awaiting proof.
6. Show architecture split between action plane and verification plane.
7. Final line: "Alexa+ gets things done. CloseLoop makes done provable."
