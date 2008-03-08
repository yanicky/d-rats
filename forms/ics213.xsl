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
	  <table class="group">
	    <tr>
	      <xsl:apply-templates select="field[
					   (@id='number') or 
					   (@id='precedence') or
					   (@id='station') or
					   (@id='place') or
					   (@id='time') or
					   (@id='date')
					   ]"/>
	    </tr>
	  </table>

	  <br/>

	  <table class="group">
	    <tr>
		<xsl:apply-templates select="field[@id='sender']"/>
	    </tr>
	    <tr>
		<xsl:apply-templates select="field[@id='recip']"/>
	    </tr>
	    <tr>
		<xsl:apply-templates select="field[@id='subject']"/>
	    </tr>
	  </table>

	  <br/>

	  <table class="group">
	    <xsl:apply-templates select="field[@id='message']"/>
	  </table>

	</body>
      </html>
</xsl:template>

    <xsl:template match="field">
      <td class="field">
	<span class="field-caption">
		<xsl:value-of select="caption"/>
	</span>
	<br/>
	<span class="field-content">
	  <xsl:value-of select="entry"/>
	</span>
      </td>
    </xsl:template>

      

</xsl:stylesheet>
