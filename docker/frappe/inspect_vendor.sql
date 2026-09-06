SELECT fieldname, fieldtype, label, idx
FROM tabDocField
WHERE parent='Vendor'
  AND (fieldtype IN ('Tab Break','Section Break','Column Break','Table')
       OR fieldname IN ('vendor_name','kyc_status','kyc_documents'))
ORDER BY idx;
