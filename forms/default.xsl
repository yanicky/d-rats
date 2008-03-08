<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
    <xsl:output method="html"/>

    <xsl:template match="form">
      <html>
	<head>
	  <style type="text/css">
	    .field {
   	       border: 1px solid black
	    }

	    .group {
	       width: 80%;
	    }

	    .field-caption {
	       font-size: 60%;
	       font-weight: bold;
	    }

	    .field-content {
	       font-family: Arial, Helvetica, sans-serif;
	    }

	  </style>
	</head>
	<body>
	  <table>
	      <xsl:apply-templates select="field"/>
	  </table>
	  </body>
	</html>
    </xsl:template>
    
    <xsl:template match="field">
      <tr class="field">
	<td>
	  <span class="field-caption">
	    <xsl:value-of select="caption"/>
	  </span>
	  </td><td>
	  <span class="field-content">
	    <xsl:value-of select="entry"/>
	  </span>
	  </td>
      </tr>
    </xsl:template>
</xsl:stylesheet>
