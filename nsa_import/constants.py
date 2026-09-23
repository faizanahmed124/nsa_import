MODE_OF_SHIPMENT = "\nBy Sea\nBy Air\nBy Road\nBy Rail\nCourier"
SHIPPING_TERMS = "\nEXW\nFCA\nFAS\nFOB\nCFR\nCIF\nCPT\nCIP\nDAP\nDPU\nDDP"
IMPORT_PAYMENT_TERMS = (
	"\nLC at Sight\nLC Usance\nAdvance TT\nTT Against Documents\nTT After Arrival"
	"\nDP (Documents against Payment)\nDA (Documents against Acceptance)\nOpen Account"
)
PAYMENT_METHODS = "\nLC\nTT\nCash\nBank Transfer\nCheque\nPay Order"

# Incoterms where the buyer pays main carriage (freight must be added to landed cost)
BUYER_PAYS_FREIGHT = ("EXW", "FCA", "FAS", "FOB")
# Incoterms where insurance is already covered by the seller
SELLER_PAYS_INSURANCE = ("CIF", "CIP", "DAP", "DPU", "DDP")
